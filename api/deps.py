"""FastAPI dependency providers — session, Plaid client.

`get_session` yields a SQLAlchemy session bound to the app's engine.
`get_plaid_client` builds a PlaidApi from environment variables.

Both are overridable in tests via app.dependency_overrides.
"""
import os
from typing import Generator

from fastapi import Depends
from plaid.api.plaid_api import PlaidApi
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from core.db import DEFAULT_DATABASE_URL, make_engine, make_session_factory
from core.plaid import PlaidEnv, make_plaid_client


_engine: Engine | None = None
_SessionLocal = None


def _ensure_engine() -> None:
    global _engine, _SessionLocal
    if _engine is None:
        url = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
        _engine = make_engine(url)
        _SessionLocal = make_session_factory(_engine)


def get_session() -> Generator[Session, None, None]:
    _ensure_engine()
    assert _SessionLocal is not None
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_plaid_client() -> PlaidApi:
    env_str = os.environ.get("PLAID_ENV", "sandbox").lower()
    env = PlaidEnv(env_str)
    client_id = os.environ.get("PLAID_CLIENT_ID", "")
    secret = os.environ.get("PLAID_SECRET", "")
    return make_plaid_client(env=env, client_id=client_id, secret=secret)


def get_engine() -> Engine:
    """Used by the startup hook (Alembic, sync orchestrator). Not a route dep."""
    _ensure_engine()
    assert _engine is not None
    return _engine


def get_session_factory():
    """Used by the orchestrator (one session per worker thread)."""
    _ensure_engine()
    assert _SessionLocal is not None
    return _SessionLocal
