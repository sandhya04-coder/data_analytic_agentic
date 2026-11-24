from sqlalchemy import inspect
from database.connection import get_engine
from security.policy_guard import get_active_policy


class SchemaInspector:
    def __init__(self, db_key: str | None = None):
        self.db_key = db_key

    @property
    def engine(self):
        return get_engine(self.db_key)

    @property
    def inspector(self):
        return inspect(self.engine)

    def get_all_tables(self) -> list[str]:
        tables = self.inspector.get_table_names()
        policy = get_active_policy()
        if policy and policy.allowed_tables is not None:
            allowed_lower = {t.lower() for t in policy.allowed_tables}
            tables = [t for t in tables if t.lower() in allowed_lower]
        return tables

    def get_table_columns(self, table_name: str) -> list[dict]:
        if table_name not in self.get_all_tables():
            raise ValueError(f"Table '{table_name}' does not exist or is restricted by RBAC policy.")

        policy = get_active_policy()
        blocked = set()
        if policy and policy.blocked_columns:
            for tbl, cols in policy.blocked_columns.items():
                if tbl.lower() == table_name.lower():
                    blocked = {c.lower() for c in cols}

        columns = self.inspector.get_columns(table_name)
        return [
            {
                "name": column["name"],
                "type": str(column["type"]),
                "nullable": column["nullable"],
                "primary_key": column.get("primary_key", False),
            }
            for column in columns
            if column["name"].lower() not in blocked
        ]
    # ... keep get_primary_keys, get_foreign_keys, get_table_relationships, get_complete_schema unchanged

    def get_primary_keys(self, table_name: str) -> list[str]:
        """Return primary key columns."""
        if table_name not in self.get_all_tables():
            raise ValueError(f"Table '{table_name}' does not exist.")

        pk = self.inspector.get_pk_constraint(table_name)
        return pk.get("constrained_columns", [])

    def get_foreign_keys(self, table_name: str) -> list[dict]:
        """Return foreign key relationships."""
        if table_name not in self.get_all_tables():
            raise ValueError(f"Table '{table_name}' does not exist.")

        foreign_keys = self.inspector.get_foreign_keys(table_name)
        return [
            {
                "columns": fk["constrained_columns"],
                "referenced_table": fk["referred_table"],
                "referenced_columns": fk["referred_columns"],
            }
            for fk in foreign_keys
        ]

    def get_table_relationships(self) -> list[dict]:
        """Return foreign key relationships across all tables."""
        relationships = []
        for table in self.get_all_tables():
            for fk in self.get_foreign_keys(table):
                relationships.append({
                    "source_table": table,
                    "source_columns": fk["columns"],
                    "target_table": fk["referenced_table"],
                    "target_columns": fk["referenced_columns"],
                })
        return relationships

    def get_complete_schema(self) -> dict:
        """Return the complete database schema."""
        return {
            table: {
                "columns": self.get_table_columns(table),
                "primary_keys": self.get_primary_keys(table),
                "foreign_keys": self.get_foreign_keys(table),
            }
            for table in self.get_all_tables()
        }