"""Shared test fixtures for the entire suite.

Specific subdirectories may add their own conftest.py for narrower fixtures.
"""
from datetime import datetime

import pytest

from core.db import (
    Account,
    Base,
    Institution,
    Item,
    make_engine,
    make_session_factory,
)


@pytest.fixture
def engine(tmp_path):
    """A fresh in-temp-file SQLite engine with all tables created via metadata."""
    db_path = tmp_path / "test.db"
    eng = make_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    """A session bound to the per-test engine."""
    SessionLocal = make_session_factory(engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def seeded_chain(session):
    """Seed institution → item → account so per-test code can insert transactions/holdings.

    Returns a dict with the inserted instances:
        {"institution": Institution, "item": Item, "account": Account}

    The Item's access_token_ciphertext is a 28-byte placeholder
    (nonce(12) + 0-byte ct + tag(16)) suitable for tests that don't actually
    decrypt. Tests that need a real ciphertext should overwrite this column.
    """
    inst = Institution(
        institution_id="ins_test",
        name="Test Bank",
        primary_color="#000000",
    )
    item = Item(
        item_id="item_test",
        institution_id="ins_test",
        access_token_ciphertext=b"\x00" * 28,
        created_at=datetime(2026, 1, 1),
    )
    acct = Account(
        account_id="acc_test",
        item_id="item_test",
        name="Checking",
        type="depository",
        subtype="checking",
        current_balance=1000.00,
        iso_currency_code="USD",
    )
    session.add_all([inst, item, acct])
    session.commit()
    return {"institution": inst, "item": item, "account": acct}


@pytest.fixture
def fake_keychain(monkeypatch):
    """Replace the `keyring` backend used by core.crypto.keychain with an in-memory dict.

    Returns the backing dict so tests can inspect or pre-seed entries.
    """
    from core.crypto import keychain

    store: dict[tuple[str, str], str] = {}
    monkeypatch.setattr(
        keychain.keyring, "get_password", lambda s, a: store.get((s, a))
    )
    monkeypatch.setattr(
        keychain.keyring, "set_password",
        lambda s, a, p: store.__setitem__((s, a), p),
    )

    def fake_delete(service, account):
        if (service, account) not in store:
            import keyring.errors
            raise keyring.errors.PasswordDeleteError("not found")
        del store[(service, account)]
    monkeypatch.setattr(keychain.keyring, "delete_password", fake_delete)

    return store


# ----- Plaid client mocks (shared across tests/plaid/ and tests/api/) -----------
from unittest.mock import MagicMock as _MagicMock


@pytest.fixture
def fake_plaid_client():
    """A MagicMock standing in for plaid.api.plaid_api.PlaidApi."""
    return _MagicMock(name="fake_plaid_client")


def _wrap(payload: dict):
    obj = _MagicMock()
    obj.to_dict.return_value = payload
    for key, value in payload.items():
        setattr(obj, key, value)
    return obj


@pytest.fixture
def make_response():
    """Wrap a dict so `.to_dict()` and attribute access both work."""
    return _wrap
