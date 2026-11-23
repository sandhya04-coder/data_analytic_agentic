
from sqlalchemy import inspect

from database.connection import get_engine


class SchemaInspector:
    """
    Dynamically inspects the database schema.

    Provides information about:
    - Tables
    - Columns
    - Primary keys
    - Foreign keys
    - Table relationships
    """

    def __init__(self):
        self.engine = get_engine()
        self.inspector = inspect(self.engine)

    def get_all_tables(self) -> list[str]:
        """Return all available table names."""
        return self.inspector.get_table_names()

    def get_table_columns(self, table_name: str) -> list[dict]:
        """Return column details for a given table."""

        if table_name not in self.get_all_tables():
            raise ValueError(f"Table '{table_name}' does not exist.")

        columns = self.inspector.get_columns(table_name)

        return [
            {
                "name": column["name"],
                "type": str(column["type"]),
                "nullable": column["nullable"],
                "primary_key": column.get("primary_key", False)
            }
            for column in columns
        ]

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
                "referenced_columns": fk["referred_columns"]
            }
            for fk in foreign_keys
        ]

    def get_table_relationships(self) -> list[dict]:
        """Return foreign key relationships across all tables."""

        relationships = []

        for table in self.get_all_tables():

            foreign_keys = self.get_foreign_keys(table)

            for fk in foreign_keys:
                relationships.append({
                    "source_table": table,
                    "source_columns": fk["columns"],
                    "target_table": fk["referenced_table"],
                    "target_columns": fk["referenced_columns"]
                })

        return relationships

    def get_complete_schema(self) -> dict:
        """Return the complete database schema."""

        schema = {}

        for table in self.get_all_tables():
            schema[table] = {
                "columns": self.get_table_columns(table),
                "primary_keys": self.get_primary_keys(table),
                "foreign_keys": self.get_foreign_keys(table)
            }

        return schema
