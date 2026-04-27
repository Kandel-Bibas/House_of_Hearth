from datetime import date

import pytest
from sqlalchemy import select

from core.db.models import (
    Account,
    Base,
    Holding,
    Institution,
    Item,
    Security,
    Transaction,
)
from core.db.session import make_engine, make_session_factory


@pytest.fixture
def session(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = make_session_factory(engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _seed_chain(session):
    """Create the FK chain: institution -> item -> account."""
    inst = Institution(institution_id="ins_1", name="Wells Fargo")
    item = Item(
        item_id="item_1",
        institution_id="ins_1",
        access_token_ciphertext=b"\x00" * 28,  # nonce(12) + ct + tag
    )
    acct = Account(
        account_id="acc_1",
        item_id="item_1",
        name="Checking",
        type="depository",
        subtype="checking",
        current_balance=1234.56,
        iso_currency_code="USD",
    )
    session.add_all([inst, item, acct])
    session.commit()


def test_institution_round_trip(session):
    inst = Institution(institution_id="ins_1", name="Wells Fargo", primary_color="#d71e28")
    session.add(inst)
    session.commit()
    fetched = session.scalar(select(Institution).where(Institution.institution_id == "ins_1"))
    assert fetched.name == "Wells Fargo"
    assert fetched.primary_color == "#d71e28"


def test_item_round_trip(session):
    _seed_chain(session)
    fetched = session.scalar(select(Item).where(Item.item_id == "item_1"))
    assert fetched.institution_id == "ins_1"
    assert fetched.access_token_ciphertext == b"\x00" * 28
    assert fetched.transactions_cursor is None


def test_account_round_trip(session):
    _seed_chain(session)
    fetched = session.scalar(select(Account).where(Account.account_id == "acc_1"))
    assert fetched.current_balance == 1234.56
    assert fetched.type == "depository"


def test_transaction_round_trip(session):
    _seed_chain(session)
    txn = Transaction(
        transaction_id="txn_1",
        account_id="acc_1",
        date=date(2026, 4, 20),
        amount=42.50,
        name="WHOLE FOODS #123",
        merchant_name="Whole Foods",
        pending=False,
        category_primary="FOOD_AND_DRINK",
        category_detailed="FOOD_AND_DRINK_GROCERIES",
        category_confidence="VERY_HIGH",
        raw_payload={"counterparties": []},
    )
    session.add(txn)
    session.commit()
    fetched = session.scalar(select(Transaction).where(Transaction.transaction_id == "txn_1"))
    assert fetched.amount == 42.50
    assert fetched.merchant_name == "Whole Foods"
    assert fetched.raw_payload == {"counterparties": []}
    assert fetched.removed_at is None


def test_security_and_holding(session):
    _seed_chain(session)
    sec = Security(security_id="sec_1", ticker_symbol="VTI", name="Vanguard Total Stock", type="etf")
    hold = Holding(
        account_id="acc_1",
        security_id="sec_1",
        quantity=10.5,
        institution_price=250.00,
        institution_value=2625.00,
    )
    session.add_all([sec, hold])
    session.commit()
    fetched = session.scalar(
        select(Holding).where(Holding.account_id == "acc_1", Holding.security_id == "sec_1")
    )
    assert fetched.quantity == 10.5
    assert fetched.institution_value == 2625.00


def test_foreign_keys_enforced(session):
    """Account requires a valid item_id."""
    bogus = Account(
        account_id="acc_x",
        item_id="item_does_not_exist",
        name="Ghost",
        type="depository",
    )
    session.add(bogus)
    with pytest.raises(Exception):
        session.commit()
