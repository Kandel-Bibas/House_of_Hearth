from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

DEFAULT_DATABASE_URL = "sqlite:///finance.db"


def make_engine(database_url: str = DEFAULT_DATABASE_URL):
    """Create a SQLAlchemy engine with SQLite pragmas configured for the app.

    WAL mode lets the FastAPI writer and the read-only MCP reader coexist.
    foreign_keys=ON enforces FK constraints (off by default in SQLite).
    synchronous=NORMAL is the right tradeoff for a single-user local app.
    """
    engine = create_engine(database_url, future=True)

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
