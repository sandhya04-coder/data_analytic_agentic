
from langchain_core.tools import tool

from database.schema_inspector import SchemaInspector
from database.connection import get_engine
from sqlalchemy import inspect, text
from sqlalchemy import Date, DateTime

@tool
def get_database_overview() -> dict:
    """
    Discover all tables available in the connected database.
    Returns the database's table names.
    """
    inspector = SchemaInspector()

    tables = inspector.get_all_tables()

    return {
        "total_tables": len(tables),
        "tables": tables
    }


@tool
def get_table_schema(table_name: str) -> dict:
    """
    Retrieve the columns, data types, primary keys and
    foreign keys of a specified database table.
    """
    inspector = SchemaInspector()

    return {
        "table_name": table_name,
        "columns": inspector.get_table_columns(table_name),
        "primary_keys": inspector.get_primary_keys(table_name),
        "foreign_keys": inspector.get_foreign_keys(table_name)
    }


@tool
def get_table_relationships() -> list[dict]:
    """
    Retrieve all declared foreign-key relationships
    between database tables.
    """
    inspector = SchemaInspector()

    return inspector.get_table_relationships()


@tool
def profile_table(
    table_name: str,
    sample_size: int = 5
) -> dict:
    """
    Profile a database table using its row count,
    column information, null counts and sample records.
    """
    engine = get_engine()
    inspector = inspect(engine)

    available_tables = inspector.get_table_names()

    if table_name not in available_tables:
        raise ValueError(
            f"Table '{table_name}' does not exist."
        )

    if not 1 <= sample_size <= 20:
        raise ValueError(
            "sample_size must be between 1 and 20."
        )

    columns = [
        column["name"]
        for column in inspector.get_columns(table_name)
    ]
    column_details = inspector.get_columns(table_name)

    date_columns = [
        c["name"] for c in column_details
        if isinstance(c["type"], (Date, DateTime))
        or any(k in str(c["type"]).upper() for k in ("DATE", "TIME"))
        or "date" in c["name"].lower()
    ]

    quoted_table = engine.dialect.identifier_preparer.quote(
        table_name
    )

    with engine.connect() as connection:

        row_count = connection.execute(
            text(f"SELECT COUNT(*) FROM {quoted_table}")
        ).scalar_one()

        null_counts = {}

        for column in columns:
            quoted_column = (
                engine.dialect.identifier_preparer.quote(column)
            )

            query = text(
                f"SELECT COUNT(*) FROM {quoted_table} "
                f"WHERE {quoted_column} IS NULL"
            )

            null_counts[column] = connection.execute(
                query
            ).scalar_one()

        date_ranges = {}

        for column in date_columns:
            quoted_column = (
                engine.dialect.identifier_preparer.quote(column)
            )

            query = text(
                f"SELECT MIN({quoted_column}), MAX({quoted_column}) "
                f"FROM {quoted_table}"
            )

            min_date, max_date = connection.execute(query).one()

            date_ranges[column] = {
                "minimum": str(min_date) if min_date is not None else None,
                "maximum": str(max_date) if max_date is not None else None
            }

        blob_cols = {
            c["name"] for c in column_details
            if "BLOB" in str(c["type"]).upper() or "LARGEBINARY" in type(c["type"]).__name__.upper()
        }
        sample_cols = [c for c in columns if c not in blob_cols]
        select_list = ", ".join(
            engine.dialect.identifier_preparer.quote(c) for c in sample_cols
        )

        sample_query = text(
            f"SELECT {select_list} FROM {quoted_table} LIMIT :sample_size"
        )
        result = connection.execute(
            sample_query,
            {"sample_size": sample_size}
        )

        sample_records = [
            dict(row._mapping)
            for row in result
        ]

    return {
        "table_name": table_name,
        "row_count": row_count,
        "columns": columns,
        "null_counts": null_counts,
        "sample_records": sample_records,
        "date_ranges": date_ranges,
    }
