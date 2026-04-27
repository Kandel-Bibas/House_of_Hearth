"""Shared test fixtures for the entire suite.

Specific subdirectories may add their own conftest.py for narrower fixtures.
"""
from datetime import date, datetime

import pytest

from core.db import (
    Account,
    Base,
    Holding,
    Institution,
    Item,
    Security,
    Transaction,
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


# ----- Queries seed (shared across tests/queries/ and tests/api/) ---------------
@pytest.fixture
def queries_seed(session, seeded_chain):
    """Extend the base seed with two more accounts (one credit, one investment),
    one security, two holdings, and 6 transactions across categories.

    Returns a dict with each created object so tests can reference them.
    """
    inst = seeded_chain["institution"]  # ins_test
    item = seeded_chain["item"]          # item_test
    base_acct = seeded_chain["account"]  # acc_test, depository checking, balance 1000.00

    credit_acct = Account(
        account_id="acc_credit",
        item_id=item.item_id,
        name="Credit Card",
        type="credit",
        subtype="credit card",
        current_balance=-250.00,        # owed
        limit_balance=5000.00,
        iso_currency_code="USD",
    )
    invest_acct = Account(
        account_id="acc_invest",
        item_id=item.item_id,
        name="Brokerage",
        type="investment",
        subtype="brokerage",
        current_balance=10000.00,
        iso_currency_code="USD",
    )
    sec = Security(
        security_id="sec_VTI",
        ticker_symbol="VTI",
        name="Vanguard Total Stock Market",
        type="etf",
        close_price=250.00,
    )
    holding = Holding(
        account_id="acc_invest",
        security_id="sec_VTI",
        quantity=40.0,
        institution_price=250.00,
        institution_value=10000.00,
    )

    txns = [
        Transaction(
            transaction_id="txn_grocery_1",
            account_id=base_acct.account_id,
            date=date(2026, 4, 1),
            amount=42.50,
            name="WHOLE FOODS",
            merchant_name="Whole Foods",
            payment_channel="in store",
            pending=False,
            category_primary="FOOD_AND_DRINK",
            category_detailed="FOOD_AND_DRINK_GROCERIES",
        ),
        Transaction(
            transaction_id="txn_grocery_2",
            account_id=base_acct.account_id,
            date=date(2026, 4, 10),
            amount=37.25,
            name="TRADER JOES",
            merchant_name="Trader Joe's",
            payment_channel="in store",
            pending=False,
            category_primary="FOOD_AND_DRINK",
            category_detailed="FOOD_AND_DRINK_GROCERIES",
        ),
        Transaction(
            transaction_id="txn_restaurant_1",
            account_id=base_acct.account_id,
            date=date(2026, 4, 5),
            amount=85.00,
            name="CHEZ PANISSE",
            merchant_name="Chez Panisse",
            payment_channel="in store",
            pending=False,
            category_primary="FOOD_AND_DRINK",
            category_detailed="FOOD_AND_DRINK_RESTAURANTS",
        ),
        Transaction(
            transaction_id="txn_gas_1",
            account_id=credit_acct.account_id,
            date=date(2026, 4, 12),
            amount=55.00,
            name="SHELL #1234",
            merchant_name="Shell",
            payment_channel="in store",
            pending=False,
            category_primary="TRANSPORTATION",
            category_detailed="TRANSPORTATION_GAS",
        ),
        Transaction(
            transaction_id="txn_paycheck",
            account_id=base_acct.account_id,
            date=date(2026, 4, 15),
            amount=-3000.00,                # negative = inflow per Plaid convention
            name="ACME CORP PAYROLL",
            merchant_name="Acme Corp",
            payment_channel="other",
            pending=False,
            category_primary="INCOME",
            category_detailed="INCOME_WAGES",
        ),
        Transaction(
            transaction_id="txn_removed",   # soft-deleted — should be excluded by default
            account_id=base_acct.account_id,
            date=date(2026, 4, 8),
            amount=20.00,
            name="OLD TXN",
            merchant_name="Old Vendor",
            payment_channel="online",
            pending=False,
            category_primary="GENERAL_MERCHANDISE",
            category_detailed="GENERAL_MERCHANDISE_OTHER",
            removed_at=datetime(2026, 4, 9),
        ),
    ]

    session.add_all([credit_acct, invest_acct, sec, holding, *txns])
    session.commit()

    return {
        "institution": inst,
        "item": item,
        "depository": base_acct,
        "credit": credit_acct,
        "investment": invest_acct,
        "security": sec,
        "holding": holding,
        "txns": txns,
    }
