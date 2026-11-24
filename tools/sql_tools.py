import sqlglot
from sqlglot import exp
from langchain_core.tools import tool
from config.settings import MAX_SQL_ROWS
from database.connection import get_engine, get_table_names
from security.policy_guard import enforce_sql_policy


def validate_sql(query: str) -> tuple[bool, str]:
    if not query or not query.strip():
        return False, "SQL query cannot be empty."
    try:
        statements = [s for s in sqlglot.parse(query, read="sqlite") if s is not None]
    except sqlglot.errors.ParseError as error:
        return False, f"SQL parsing failed: {error}"
    if len(statements) != 1:
        return False, "Only one SQL statement is allowed."
    if not isinstance(statements[0], exp.Query):
        return False, "Only SELECT queries are allowed."
    return True, "SQL query is valid."


def validate_tables(query: str) -> tuple[bool, str]:
    """Check that every referenced table really exists."""
    tree = sqlglot.parse_one(query, read="sqlite")
    cte_names = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    known = {t.lower() for t in get_table_names()}
    unknown = sorted({
        t.name for t in tree.find_all(exp.Table)
        if t.name.lower() not in cte_names and t.name.lower() not in known
    })
    if unknown:
        return False, f"Unknown tables: {unknown}. Available tables: {sorted(get_table_names())}"
    return True, "OK"


def run_query(query: str) -> dict:
    is_valid, message = validate_sql(query)
    if not is_valid:
        return {"success": False, "error": message, "error_type": "validation"}
    ok, message = validate_tables(query)
    if not ok:
        return {"success": False, "error": message, "error_type": "validation"}

    # Layer 3 Security: Enforce RBAC (tables/columns) + ABAC (row-level WHERE injection)
    allowed, governed_query, sec_error = enforce_sql_policy(query, dialect="sqlite")
    if not allowed:
        return {"success": False, "error": sec_error, "error_type": "security_policy"}

    try:
        with get_engine().connect() as connection:
            result = connection.exec_driver_sql(governed_query)
            columns = list(result.keys())
            fetched = result.fetchmany(MAX_SQL_ROWS + 1)
    except Exception as error:
        return {"success": False, "error": str(error), "error_type": "execution"}

    truncated = len(fetched) > MAX_SQL_ROWS
    rows = [dict(r._mapping) for r in fetched[:MAX_SQL_ROWS]]
    return {
        "success": True,
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "truncated": truncated,
        "max_rows": MAX_SQL_ROWS,
        "executed_sql": governed_query,
    }


def explain_query(query: str) -> dict:
    """EXPLAIN QUERY PLAN: catches bad columns without running the query."""
    is_valid, message = validate_sql(query)
    if not is_valid:
        return {"success": False, "error": message, "error_type": "validation"}
    allowed, governed_query, sec_error = enforce_sql_policy(query, dialect="sqlite")
    if not allowed:
        return {"success": False, "error": sec_error, "error_type": "security_policy"}
    try:
        with get_engine().connect() as connection:
            plan = connection.exec_driver_sql(f"EXPLAIN QUERY PLAN {governed_query}").fetchall()
    except Exception as error:
        return {"success": False, "error": str(error), "error_type": "explain"}
    steps = [str(row[-1]) for row in plan]
    return {
        "success": True,
        "plan": steps,
        "full_table_scans": [s for s in steps if s.startswith("SCAN")],
    }


@tool
def execute_sql(query: str) -> dict:
    """Validate, enforce RBAC/ABAC policy, and execute a read-only SQL query."""
    return run_query(query)


@tool
def explain_sql(query: str) -> dict:
    """Return the SQLite execution plan for a policy-governed read-only query."""
    return explain_query(query)