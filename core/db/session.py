import json
from datetime import date, datetime

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

DEFAULT_DATABASE_URL = "sqlite:///finance.db"


def _json_default(obj):
    """JSON encoder fallback for types stdlib json doesn't handle.

    Plaid's `.to_dict()` returns nested dicts that include `datetime.date`
    values (e.g., transaction.authorized_date inside raw_payload).
    """
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _json_serializer(obj):
    return json.dumps(obj, default=_json_default)


def make_engine(database_url: str = DEFAULT_DATABASE_URL):
    """Create a SQLAlchemy engine with SQLite pragmas configured for the app.

    WAL mode lets the FastAPI writer and the read-only MCP reader coexist.
    foreign_keys=ON enforces FK constraints (off by default in SQLite).
    synchronous=NORMAL is the right tradeoff for a single-user local app.
    """
    engine = create_engine(database_url, future=True, json_serializer=_json_serializer)

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

    return engine


def make_session_factory(engine):
    """Return a sessionmaker bound to the given engine."""
    return sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
        future=True,
    )
