from collections import deque
from contextvars import ContextVar
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from sqlalchemy import inspect
import sqlglot
from sqlglot import exp

from database.connection import get_engine


@dataclass(frozen=True)
class AccessPolicy:
    policy_id: str
    display_name: str
    db_key: str
    allowed_tables: set[str] | None = None
    blocked_columns: dict[str, set[str]] = field(default_factory=dict)
    row_filters: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SSOUser:
    email: str
    full_name: str
    title: str
    db_key: str
    policy_key: str
    claims: dict[str, str]


_ACTIVE_POLICY: ContextVar[AccessPolicy | None] = ContextVar("active_policy", default=None)
_FK_GRAPH_CACHE: dict[str, dict[str, list[tuple[str, str, str]]]] = {}

DEFAULT_POLICY_PATH = Path(__file__).resolve().parent.parent / "config" / "policies.json"

DEFAULT_POLICY_PATH = Path(__file__).resolve().parent.parent / "config" / "policies.json"
DEFAULT_USERS_PATH = Path(__file__).resolve().parent.parent / "config" / "users.json"


def load_sso_users(users_path: Path = DEFAULT_USERS_PATH) -> dict[str, SSOUser]:
    """Load SSO user personas dynamically from external JSON config."""
    if not users_path.exists():
        return {}
    with open(users_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return {
        u["email"]: SSOUser(
            email=u["email"],
            full_name=u["full_name"],
            title=u["title"],
            db_key=u["db_key"],
            policy_key=u["policy_key"],
            claims=u.get("claims", {}),
        )
        for u in data.get("users", [])
    }


SSO_USERS: dict[str, SSOUser] = load_sso_users()

# ---------------------------------------------------------------------------
# 1. External Policy Loader & Dynamic SSO Claim Binding
# ---------------------------------------------------------------------------

def _render_claim_template(template: str, claims: dict[str, str]) -> str:
    """Safely substitute {claim_key} placeholders with SQL-escaped SSO claim values."""
    def _replace(match: re.Match) -> str:
        key = match.group(1)
        if key not in claims:
            raise ValueError(f"Missing required SSO claim '{key}' for policy template '{template}'.")
        # Escape single quotes to prevent claim-based SQL injection
        return str(claims[key]).replace("'", "''")

    return re.sub(r"\{([a-zA-Z0-9_]+)\}", _replace, template)


def load_policy_catalog(policy_path: Path = DEFAULT_POLICY_PATH) -> dict:
    with open(policy_path, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_policy_for_user(user: SSOUser, policy_path: Path = DEFAULT_POLICY_PATH) -> AccessPolicy:
    """Build an AccessPolicy dynamically from external JSON config + user's SSO claims."""
    catalog = load_policy_catalog(policy_path)
    db_policies = catalog.get("databases", {}).get(user.db_key, {})
    raw = db_policies.get(user.policy_key)

    if not raw:
        return AccessPolicy(
            policy_id=user.policy_key,
            display_name=f"{user.title} (Default Policy)",
            db_key=user.db_key,
        )

    display_name = _render_claim_template(raw.get("display_name", user.policy_key), user.claims)
    allowed = set(raw["allowed_tables"]) if raw.get("allowed_tables") is not None else None
    blocked = {tbl: set(cols) for tbl, cols in raw.get("blocked_columns", {}).items()}
    row_filters = {
        tbl: _render_claim_template(expr, user.claims)
        for tbl, expr in raw.get("row_filters", {}).items()
    }

    return AccessPolicy(
        policy_id=user.policy_key,
        display_name=display_name,
        db_key=user.db_key,
        allowed_tables=allowed,
        blocked_columns=blocked,
        row_filters=row_filters,
    )


def get_policies_for_db(
    db_key: str,
    sample_claims: dict[str, str] | None = None,
    policy_path: Path = DEFAULT_POLICY_PATH,
) -> dict[str, AccessPolicy]:
    """Return available policy templates for UI selection or fallback inspection."""
    catalog = load_policy_catalog(policy_path)
    db_policies = catalog.get("databases", {}).get(db_key, {})
    if not db_policies:
        return {
            "exec_admin": AccessPolicy(
                policy_id="exec_admin",
                display_name="Executive Admin (Full Access)",
                db_key=db_key,
            )
        }

    claims = sample_claims or {}
    result: dict[str, AccessPolicy] = {}
    for pol_id, raw in db_policies.items():
        try:
            dummy_user = SSOUser("", "", pol_id, db_key, pol_id, claims)
            result[pol_id] = resolve_policy_for_user(dummy_user, policy_path)
        except ValueError:
            # Template requires user-specific claims (e.g. assigned_state)
            result[pol_id] = AccessPolicy(
                policy_id=pol_id,
                display_name=raw.get("display_name", pol_id),
                db_key=db_key,
                allowed_tables=set(raw["allowed_tables"]) if raw.get("allowed_tables") is not None else None,
                blocked_columns={t: set(c) for t, c in raw.get("blocked_columns", {}).items()},
                row_filters=raw.get("row_filters", {}),
            )
    return result


def set_active_policy(policy: AccessPolicy | None) -> None:
    _ACTIVE_POLICY.set(policy)


def get_active_policy() -> AccessPolicy | None:
    return _ACTIVE_POLICY.get()


# ---------------------------------------------------------------------------
# 2. Checkpoint 1: Schema Masking
# ---------------------------------------------------------------------------

def filter_schema_for_policy(schema: dict, policy: AccessPolicy | None) -> dict:
    """Strip unauthorized tables & columns before LLM planning/SQL generation."""
    if policy is None:
        return schema

    allowed_lower = {t.lower() for t in policy.allowed_tables} if policy.allowed_tables is not None else None
    blocked_cols_lower = {
        tbl.lower(): {c.lower() for c in cols}
        for tbl, cols in policy.blocked_columns.items()
    }

    filtered: dict = {}
    for table_name, meta in schema.items():
        if allowed_lower is not None and table_name.lower() not in allowed_lower:
            continue

        restricted = blocked_cols_lower.get(table_name.lower(), set())
        filtered[table_name] = {
            **meta,
            "columns": [c for c in meta.get("columns", []) if c["name"].lower() not in restricted],
        }
    return filtered


# ---------------------------------------------------------------------------
# 3. Dynamic Foreign-Key Graph & Transitive EXISTS AST Synthesizer
# ---------------------------------------------------------------------------

def _get_fk_adjacency(db_key: str) -> dict[str, list[tuple[str, str, str]]]:
    """
    Introspect live database relationships via SQLAlchemy Inspector:
      1. Uses formal FOREIGN KEY constraints when declared (e.g., Northwind).
      2. Falls back to automatic PK / <singular_table>_id column matching for
         CSV-imported SQLite databases lacking FK DDL (e.g., Olist).
    Returns bidirectional adjacency map:
      table_lower -> [(neighbor_table_actual, local_col, remote_col), ...]
    """
    if db_key in _FK_GRAPH_CACHE:
        return _FK_GRAPH_CACHE[db_key]

    inspector = inspect(get_engine())
    tables = inspector.get_table_names()
    adj: dict[str, list[tuple[str, str, str]]] = {t.lower(): [] for t in tables}

    # 1. Formal FOREIGN KEY constraints
    for tbl in tables:
        for fk in inspector.get_foreign_keys(tbl):
            ref_tbl = fk.get("referred_table")
            local_cols = fk.get("constrained_columns") or []
            remote_cols = fk.get("referred_columns") or []
            if not ref_tbl or not local_cols or not remote_cols:
                continue

            l_col, r_col = local_cols[0], remote_cols[0]
            adj[tbl.lower()].append((ref_tbl, l_col, r_col))
            adj.setdefault(ref_tbl.lower(), []).append((tbl, r_col, l_col))

    # 2. Schema-convention fallback when no formal FKs exist (CSV-imported DBs)
    if not any(adj.values()):
        pk_by_col: dict[str, tuple[str, str]] = {}
        for tbl in tables:
            pk_cols = inspector.get_pk_constraint(tbl).get("constrained_columns") or []
            if len(pk_cols) == 1:
                pk_by_col[pk_cols[0].lower()] = (tbl, pk_cols[0])
            else:
                singular = tbl[:-1] if tbl.lower().endswith("s") else tbl
                candidate = f"{singular.lower()}_id"
                for col_info in inspector.get_columns(tbl):
                    if col_info["name"].lower() == candidate:
                        pk_by_col[candidate] = (tbl, col_info["name"])

        for tbl in tables:
            for col_info in inspector.get_columns(tbl):
                col_name = col_info["name"]
                match = pk_by_col.get(col_name.lower())
                if match and match[0].lower() != tbl.lower():
                    ref_tbl, ref_col = match
                    adj[tbl.lower()].append((ref_tbl, col_name, ref_col))
                    adj[ref_tbl.lower()].append((tbl, ref_col, col_name))

    _FK_GRAPH_CACHE[db_key] = adj
    return adj


def _find_fk_path(
    adj: dict[str, list[tuple[str, str, str]]],
    start_table_lower: str,
    target_table_lower: str,
) -> list[tuple[str, str, str]] | None:
    """BFS shortest join path from queried table -> ABAC-protected parent table."""
    if start_table_lower == target_table_lower or start_table_lower not in adj:
        return None

    queue: deque[tuple[str, list[tuple[str, str, str]]]] = deque([(start_table_lower, [])])
    visited = {start_table_lower}

    while queue:
        curr, path = queue.popleft()
        for next_tbl, local_col, remote_col in adj.get(curr, []):
            nxt_lower = next_tbl.lower()
            if nxt_lower in visited:
                continue
            new_path = path + [(next_tbl, local_col, remote_col)]
            if nxt_lower == target_table_lower:
                return new_path
            visited.add(nxt_lower)
            queue.append((nxt_lower, new_path))

    return None


def _build_transitive_exists_ast(
    queried_alias: str,
    fk_path: list[tuple[str, str, str]],
    row_predicate_sql: str,
    dialect: str = "sqlite",
) -> exp.Exists:
    """
    Dynamically synthesize an EXISTS subquery AST from a discovered FK path:
      EXISTS (
        SELECT 1 FROM <hop_1> _abac_0
        [JOIN <hop_2> _abac_1 ON _abac_0.<fk> = _abac_1.<pk>]
        WHERE _abac_0.<fk> = <queried_alias>.<local_col>
          AND _abac_<last>.<row_predicate>
      )
    """
    first_tbl, first_local_col, first_remote_col = fk_path[0]
    first_alias = "_abac_0"

    subq = (
        exp.select(exp.Literal.number(1))
        .from_(exp.table_(first_tbl, alias=first_alias, quoted=True))
    )

    prev_alias = first_alias
    for idx, (hop_tbl, local_col, remote_col) in enumerate(fk_path[1:], start=1):
        hop_alias = f"_abac_{idx}"
        on_cond = exp.EQ(
            this=exp.column(local_col, table=prev_alias, quoted=True),
            expression=exp.column(remote_col, table=hop_alias, quoted=True),
        )
        subq = subq.join(exp.table_(hop_tbl, alias=hop_alias, quoted=True), on=on_cond)
        prev_alias = hop_alias

    # Link hop 0 back to outer queried table alias
    link_cond = exp.EQ(
        this=exp.column(first_remote_col, table=first_alias, quoted=True),
        expression=exp.column(first_local_col, table=queried_alias, quoted=True),
    )

    # Qualify unqualified columns in row_predicate with the terminal ABAC table alias
    pred_expr = sqlglot.parse_one(row_predicate_sql, read=dialect)
    for col in pred_expr.find_all(exp.Column):
        if not col.table:
            col.set("table", exp.to_identifier(prev_alias))

    subq = subq.where(exp.and_(link_cond, pred_expr))
    return exp.Exists(this=subq)


# ---------------------------------------------------------------------------
# 4. Checkpoint 2: AST Policy Enforcement
# ---------------------------------------------------------------------------

def enforce_sql_policy(
    sql: str,
    policy: AccessPolicy | None = None,
    dialect: str = "sqlite",
) -> tuple[bool, str, str]:
    """
    Deterministically validate RBAC and inject direct + transitive ABAC row-level WHERE
    predicates via sqlglot AST rewriting. Zero hardcoded schema names.
    """
    active = policy if policy is not None else get_active_policy()
    if active is None:
        return True, sql, ""

    try:
        parsed = sqlglot.parse_one(sql, read=dialect)
    except Exception as exc:
        return False, "", f"SQL Security Parser Error: {exc}"

    if not isinstance(parsed, (exp.Select, exp.Union)):
        return False, "", "Security Violation: Only read-only SELECT statements are permitted."

    cte_names = {cte.alias_or_name.lower() for cte in parsed.find_all(exp.CTE)}
    alias_to_table: dict[str, str] = {}

    # 1. RBAC Table Validation
    for tbl in parsed.find_all(exp.Table):
        t_name = tbl.name
        if not t_name or t_name.lower() in cte_names:
            continue
        alias_to_table[tbl.alias_or_name.lower()] = t_name

        if active.allowed_tables is not None:
            allowed_lower = {t.lower() for t in active.allowed_tables}
            if t_name.lower() not in allowed_lower:
                return False, "", f"RBAC Access Denied: Role '{active.display_name}' cannot query table '{t_name}'."

    # 2. RBAC Column Validation (including SELECT * on tables with restricted columns)
    if active.blocked_columns:
        blocked_map = {t.lower(): {c.lower() for c in cols} for t, cols in active.blocked_columns.items()}

        for star in parsed.find_all(exp.Star):
            parent_select = star.find_ancestor(exp.Select)
            if parent_select:
                for tbl in parent_select.find_all(exp.Table):
                    if tbl.find_ancestor(exp.Select) is parent_select and tbl.name.lower() in blocked_map:
                        return (
                            False,
                            "",
                            f"RBAC Access Denied: 'SELECT *' is blocked on '{tbl.name}' because restricted columns exist.",
                        )

        for col in parsed.find_all(exp.Column):
            col_name = col.name.lower()
            tbl_ref = col.table.lower() if col.table else ""
            resolved_table = alias_to_table.get(tbl_ref, tbl_ref)

            for restricted_tbl, restricted_cols in blocked_map.items():
                if col_name in restricted_cols:
                    if not resolved_table or resolved_table.lower() == restricted_tbl:
                        return (
                            False,
                            "",
                            f"RBAC Access Denied: Column '{col.name}' on '{restricted_tbl}' is restricted for role '{active.display_name}'.",
                        )

    # 3. Direct + Dynamic Transitive ABAC Row-Level Predicate Injection
    if active.row_filters:
        row_filters_lower = {t.lower(): pred for t, pred in active.row_filters.items()}
        fk_adj = _get_fk_adjacency(active.db_key)

        for select_node in parsed.find_all(exp.Select):
            direct_tables = {
                t.name.lower(): t.alias_or_name
                for t in select_node.find_all(exp.Table)
                if t.find_ancestor(exp.Select) is select_node and t.name.lower() not in cte_names
            }

            # 3a. Direct ABAC predicates on queried tables
            for tbl_lower, qualifier in direct_tables.items():
                predicate_sql = row_filters_lower.get(tbl_lower)
                if predicate_sql:
                    predicate_expr = sqlglot.parse_one(predicate_sql, read=dialect)
                    for p_col in predicate_expr.find_all(exp.Column):
                        if not p_col.table:
                            p_col.set("table", exp.to_identifier(qualifier))
                    select_node.where(predicate_expr, append=True, copy=False)

            # 3b. Dynamic Transitive ABAC via FK graph BFS when protected table isn't directly joined
            for protected_tbl_lower, predicate_sql in row_filters_lower.items():
                if protected_tbl_lower in direct_tables:
                    continue  # Already covered by direct filter above

                for queried_tbl_lower, qualifier in direct_tables.items():
                    fk_path = _find_fk_path(fk_adj, queried_tbl_lower, protected_tbl_lower)
                    if fk_path:
                        exists_ast = _build_transitive_exists_ast(
                            queried_alias=qualifier,
                            fk_path=fk_path,
                            row_predicate_sql=predicate_sql,
                            dialect=dialect,
                        )
                        select_node.where(exists_ast, append=True, copy=False)
                        break

    return True, parsed.sql(dialect=dialect), ""