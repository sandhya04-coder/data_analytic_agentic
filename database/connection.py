from contextvars import ContextVar
from pathlib import Path
import sqlite3
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

# Project root & database directory
BASE_DIR = Path(__file__).resolve().parents[1]
DB_DIR = BASE_DIR / "database"

_ACTIVE_DB_KEY: ContextVar[str] = ContextVar("active_db_key", default="northwind")
_ENGINES: dict[str, Engine] = {}


def list_available_databases() -> dict[str, Path]:
    """Auto-discover all .sqlite and .db files inside the database/ folder."""
    available: dict[str, Path] = {}
    if DB_DIR.exists():
        for pattern in ("*.sqlite", "*.db"):
            for db_file in sorted(DB_DIR.glob(pattern)):
                available[db_file.stem] = db_file
    if not available:
        raise FileNotFoundError(
            f"No SQLite databases found in: {DB_DIR}\n"
            "Please place northwind.sqlite or olist.sqlite inside the database folder."
        )
    return available


def set_active_database(db_key: str) -> None:
    """Switch the active tenant database for the current execution context."""
    available = list_available_databases()
    if db_key not in available:
        raise ValueError(f"Unknown database '{db_key}'. Available: {list(available.keys())}")
    _ACTIVE_DB_KEY.set(db_key)


def get_active_database() -> str:
    return _ACTIVE_DB_KEY.get()


def _create_readonly_engine(db_path: Path) -> Engine:
    def _ro_connect():
        return sqlite3.connect(
            f"file:{db_path.as_posix()}?mode=ro",
            uri=True,
            check_same_thread=False,
        )

    return create_engine("sqlite://", creator=_ro_connect)


def get_engine(db_key: str | None = None) -> Engine:
    """Return the read-only SQLAlchemy database engine for the active (or specified) database."""
    target = db_key or _ACTIVE_DB_KEY.get()
    available = list_available_databases()
    if target not in available:
        target = next(iter(available))

    if target not in _ENGINES:
        _ENGINES[target] = _create_readonly_engine(available[target])
    return _ENGINES[target]


def test_connection(db_key: str | None = None) -> bool:
    """Test whether the active database connection is working."""
    try:
        with get_engine(db_key).connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception as error:
        print(f"Database connection failed: {error}")
        return False


def get_table_names(db_key: str | None = None) -> list[str]:
    """Retrieve all table names from the active SQLite database."""
    query = text("""
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        AND name NOT LIKE 'sqlite_%'
        ORDER BY name;
    """)
    with get_engine(db_key).connect() as connection:
        result = connection.execute(query)
        return [row[0] for row in result]