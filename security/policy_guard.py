from contextvars import ContextVar
from dataclasses import dataclass, field
import sqlglot
from sqlglot import exp


@dataclass(frozen=True)
class AccessPolicy:
    policy_id: str
    display_name: str
    db_key: str
    allowed_tables: set[str] | None = None  # None = all tables in db_key allowed
    blocked_columns: dict[str, set[str]] = field(default_factory=dict)  # {"table": {"col1", "col2"}}
    row_filters: dict[str, str] = field(default_factory=dict)           # {"table": "col = 'VAL'"}

@dataclass(frozen=True)
class SSOUser:
    email: str
    full_name: str
    title: str
    db_key: str
    policy_key: str
    claims: dict[str, str]


SSO_USERS: dict[str, SSOUser] = {
    "ana.exec@olist.com.br": SSOUser(
        email="ana.exec@olist.com.br",
        full_name="Ana Costa",
        title="VP of E-Commerce (Olist)",
        db_key="olist",
        policy_key="exec_admin",
        claims={"tenant": "olist", "role": "executive_admin", "clearance": "ALL"},
    ),
    "carlos.sp@olist.com.br": SSOUser(
        email="carlos.sp@olist.com.br",
        full_name="Carlos Silva",
        title="State Manager • São Paulo (Olist)",
        db_key="olist",
        policy_key="sp_state_mgr",
        claims={"tenant": "olist", "role": "regional_manager", "assigned_state": "SP"},
    ),
    "julia.fin@olist.com.br": SSOUser(
        email="julia.fin@olist.com.br",
        full_name="Julia Mendes",
        title="Financial Controller (Olist)",
        db_key="olist",
        policy_key="finance_analyst",
        claims={"tenant": "olist", "role": "finance_analyst", "scope": "orders,payments,items"},
    ),
    "sarah.exec@northwind.com": SSOUser(
        email="sarah.exec@northwind.com",
        full_name="Sarah Jenkins",
        title="Chief Revenue Officer (Northwind)",
        db_key="northwind",
        policy_key="exec_admin",
        claims={"tenant": "northwind", "role": "executive_admin", "clearance": "ALL"},
    ),
    "marc.eu@northwind.com": SSOUser(
        email="marc.eu@northwind.com",
        full_name="Marc Laurent",
        title="Regional Director • Western Europe (Northwind)",
        db_key="northwind",
        policy_key="we_regional_mgr",
        claims={"tenant": "northwind", "role": "regional_manager", "assigned_region": "Western Europe"},
    ),
}
# Multi-tenant RBAC + ABAC policy catalog
POLICIES_BY_DB: dict[str, dict[str, AccessPolicy]] = {
    "northwind": {
        "exec_admin": AccessPolicy(
            policy_id="exec_admin",
            display_name="Executive Admin (Full Access)",
            db_key="northwind",
        ),
        "we_regional_mgr": AccessPolicy(
            policy_id="we_regional_mgr",
            display_name="Regional Manager • Western Europe (ABAC)",
            db_key="northwind",
            blocked_columns={"Employees": {"BirthDate", "HomePhone", "Address", "Notes"}},
            row_filters={"Orders": "ShipRegion = 'Western Europe'"},
        ),
        "sales_analyst": AccessPolicy(
            policy_id="sales_analyst",
            display_name="Sales Analyst • No HR/Suppliers (RBAC)",
            db_key="northwind",
            allowed_tables={"Orders", "Order Details", "Products", "Categories", "Customers"},
        ),
    },
    "olist": {
        "exec_admin": AccessPolicy(
            policy_id="exec_admin",
            display_name="Executive Admin (Full Access)",
            db_key="olist",
        ),
        "sp_state_mgr": AccessPolicy(
            policy_id="sp_state_mgr",
            display_name="State Manager • São Paulo SP (ABAC)",
            db_key="olist",
            blocked_columns={"customers": {"customer_zip_code_prefix"}, "sellers": {"seller_zip_code_prefix"}},
            row_filters={"customers": "customer_state = 'SP'"},
        ),
        "finance_analyst": AccessPolicy(
            policy_id="finance_analyst",
            display_name="Finance Analyst • Orders & Payments Only (RBAC)",
            db_key="olist",
            allowed_tables={"orders", "order_payments", "order_items"},
        ),
    },
}

_ACTIVE_POLICY: ContextVar[AccessPolicy | None] = ContextVar("active_policy", default=None)


def get_policies_for_db(db_key: str) -> dict[str, AccessPolicy]:
    if db_key in POLICIES_BY_DB:
        return POLICIES_BY_DB[db_key]
    return {
        "exec_admin": AccessPolicy(
            policy_id="exec_admin",
            display_name="Executive Admin (Full Access)",
            db_key=db_key,
        )
    }


def set_active_policy(policy: AccessPolicy | None) -> None:
    _ACTIVE_POLICY.set(policy)


def get_active_policy() -> AccessPolicy | None:
    return _ACTIVE_POLICY.get()


def filter_schema_for_policy(schema: dict, policy: AccessPolicy | None) -> dict:
    """Checkpoint 1: Strip unauthorized tables & columns before LLM planning/SQL generation."""
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


def enforce_sql_policy(
    sql: str,
    policy: AccessPolicy | None = None,
    dialect: str = "sqlite",
) -> tuple[bool, str, str]:
    """
    Checkpoint 2: Deterministically validate RBAC and inject ABAC row-level WHERE predicates
    via sqlglot AST rewriting.
    Returns: (is_allowed, rewritten_sql, error_message)
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

    # 3. ABAC Row-Level Predicate Injection
    if active.row_filters:
        for select_node in parsed.find_all(exp.Select):
            for tbl in select_node.find_all(exp.Table):
                if tbl.find_ancestor(exp.Select) is not select_node:
                    continue
                for target_tbl, predicate_sql in active.row_filters.items():
                    if tbl.name.lower() == target_tbl.lower():
                        qualifier = tbl.alias_or_name
                        predicate_expr = sqlglot.parse_one(predicate_sql, read=dialect)
                        for p_col in predicate_expr.find_all(exp.Column):
                            if not p_col.table:
                                p_col.set("table", exp.to_identifier(qualifier))
                        select_node.where(predicate_expr, append=True, copy=False)

    # 3b. Transitive ABAC Protection for Olist fact tables when 'customers' isn't directly joined
    if active.db_key == "olist" and "customers" in {k.lower() for k in active.row_filters}:
        cust_filter = next(v for k, v in active.row_filters.items() if k.lower() == "customers")
        for select_node in parsed.find_all(exp.Select):
            direct_tables = {
                t.name.lower(): t.alias_or_name
                for t in select_node.find_all(exp.Table)
                if t.find_ancestor(exp.Select) is select_node
            }
            if "customers" not in direct_tables:
                if "orders" in direct_tables:
                    o_alias = direct_tables["orders"]
                    subq = (
                        f"EXISTS (SELECT 1 FROM customers _abac_c "
                        f"WHERE _abac_c.customer_id = {o_alias}.customer_id AND _abac_c.{cust_filter})"
                    )
                    select_node.where(sqlglot.parse_one(subq, read=dialect), append=True, copy=False)
                elif "order_items" in direct_tables:
                    oi_alias = direct_tables["order_items"]
                    subq = (
                        f"EXISTS (SELECT 1 FROM orders _abac_o "
                        f"JOIN customers _abac_c ON _abac_o.customer_id = _abac_c.customer_id "
                        f"WHERE _abac_o.order_id = {oi_alias}.order_id AND _abac_c.{cust_filter})"
                    )
                    select_node.where(sqlglot.parse_one(subq, read=dialect), append=True, copy=False)

    return True, parsed.sql(dialect=dialect), ""