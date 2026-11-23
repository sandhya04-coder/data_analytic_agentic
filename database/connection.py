
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

# Project root directory
BASE_DIR = Path(__file__).resolve().parents[1]

# Northwind database location
DATABASE_PATH = BASE_DIR / "database" / "northwind.sqlite"

# Check whether database exists
if not DATABASE_PATH.exists():
    raise FileNotFoundError(
        f"Northwind database not found at: {DATABASE_PATH}\n"
        "Please place northwind.sqlite inside the database folder."
    )

# Create SQLite connection URL
import sqlite3
from sqlalchemy import create_engine

def _ro_connect():
    return sqlite3.connect(
        f"file:{DATABASE_PATH.as_posix()}?mode=ro",
        uri=True,
        check_same_thread=False
    )

engine: Engine = create_engine("sqlite://", creator=_ro_connect)


def get_engine() -> Engine:
    """Return the SQLAlchemy database engine."""
    return engine


def test_connection() -> bool:
    """Test whether the database connection is working."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        return True

    except Exception as error:
        print(f"Database connection failed: {error}")
        return False


def get_table_names() -> list[str]:
    """Retrieve all table names from the SQLite database."""
    query = text("""
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        AND name NOT LIKE 'sqlite_%'
        ORDER BY name;
    """)

    with engine.connect() as connection:
        result = connection.execute(query)

        return [row[0] for row in result]
