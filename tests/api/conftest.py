"""TestClient that overrides the session dependency to use a per-test in-memory DB."""
import pytest
from fastapi.testclient import TestClient

from api.deps import get_session, get_plaid_client
from api.main import app
from core.db import Base, make_session_factory


@pytest.fixture
def client(engine):
    """A FastAPI TestClient with get_session bound to the per-test engine."""
    Base.metadata.create_all(engine)
    SessionLocal = make_session_factory(engine)

    def _override_session():
        s = SessionLocal()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_session] = _override_session

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture
def client_with_plaid(client, fake_plaid_client):
    """As `client`, but get_plaid_client also overridden to the MagicMock."""
    app.dependency_overrides[get_plaid_client] = lambda: fake_plaid_client
    yield client
    # cleanup happens in the `client` fixture's teardown
