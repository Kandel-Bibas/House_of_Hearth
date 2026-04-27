"""TestClient that overrides the session dependency to use a per-test in-memory DB."""
import os
os.environ["FINANCE_TRACKER_SKIP_STARTUP"] = "1"

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api import deps as api_deps
from api.deps import get_session, get_plaid_client
from api.main import app
from core.db import Base, make_session_factory


@pytest.fixture
def client(engine, monkeypatch):
    """A FastAPI TestClient with get_session bound to the per-test engine.

    Also points the module-global session factory and Plaid client at the test
    engine / a no-op mock so background tasks (e.g. the /sync route) don't
    touch the production DB or the network.
    """
    Base.metadata.create_all(engine)
    SessionLocal = make_session_factory(engine)

    def _override_session():
        s = SessionLocal()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_session] = _override_session

    # Point the module-global engine/factory used by background tasks
    # (sync route, startup hook helpers) at the test engine.
    monkeypatch.setattr(api_deps, "_engine", engine)
    monkeypatch.setattr(api_deps, "_SessionLocal", SessionLocal)
    # Stop background sync tasks from making real Plaid calls.
    monkeypatch.setattr(api_deps, "get_plaid_client", lambda: MagicMock())

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture
def client_with_plaid(client, fake_plaid_client):
    """As `client`, but get_plaid_client also overridden to the MagicMock."""
    app.dependency_overrides[get_plaid_client] = lambda: fake_plaid_client
    yield client
    # cleanup happens in the `client` fixture's teardown
