from datetime import date, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from core.db import Item, Transaction
from core.plaid.sync import apply_sync_page


# ---------- helpers ----------------------------------------------------------


def _txn(transaction_id: str, account_id: str = "acc_test", amount: float = 10.0, **kw):
    """Build a Plaid-shaped transaction dict (matches what /transactions/sync returns)."""
    base = {
        "transaction_id": transaction_id,
        "account_id": account_id,
        "date": "2026-04-20",
        "authorized_date": None,
        "amount": amount,
        "iso_currency_code": "USD",
        "name": "TEST TXN",
        "merchant_name": "Test Merchant",
        "payment_channel": "in store",
        "pending": False,
        "personal_finance_category": {
            "primary": "FOOD_AND_DRINK",
            "detailed": "FOOD_AND_DRINK_GROCERIES",
            "confidence_level": "VERY_HIGH",
        },
        "counterparties": [],
        "location": {},
        "payment_meta": {},
    }
    base.update(kw)
    return base


def _page(*, added=None, modified=None, removed=None, has_more=False, next_cursor="c1"):
    return SimpleNamespace(
        added=added or [],
        modified=modified or [],
        removed=removed or [],  # list of {"transaction_id": "..."}
        has_more=has_more,
        next_cursor=next_cursor,
    )


# ---------- happy paths ------------------------------------------------------


def test_apply_page_inserts_added_transactions(session, seeded_chain):
    page = _page(added=[_txn("txn_1"), _txn("txn_2")])
    apply_sync_page(session, item_id=seeded_chain["item"].item_id, page=page)
    session.commit()

    txns = session.scalars(select(Transaction)).all()
    assert {t.transaction_id for t in txns} == {"txn_1", "txn_2"}
    assert txns[0].category_primary == "FOOD_AND_DRINK"
    assert txns[0].category_detailed == "FOOD_AND_DRINK_GROCERIES"
    assert txns[0].category_confidence == "VERY_HIGH"


def test_apply_page_overwrites_modified_transactions(session, seeded_chain):
    page1 = _page(added=[_txn("txn_1", amount=10.0, name="OLD")])
    apply_sync_page(session, item_id=seeded_chain["item"].item_id, page=page1)
    session.commit()

    page2 = _page(modified=[_txn("txn_1", amount=99.99, name="NEW")])
    apply_sync_page(session, item_id=seeded_chain["item"].item_id, page=page2)
    session.commit()

    txn = session.scalar(select(Transaction).where(Transaction.transaction_id == "txn_1"))
    assert txn.amount == 99.99
    assert txn.name == "NEW"


def test_apply_page_soft_deletes_removed_transactions(session, seeded_chain):
    page1 = _page(added=[_txn("txn_1")])
    apply_sync_page(session, item_id=seeded_chain["item"].item_id, page=page1)
    session.commit()

    page2 = _page(removed=[{"transaction_id": "txn_1"}])
    apply_sync_page(session, item_id=seeded_chain["item"].item_id, page=page2)
    session.commit()

    txn = session.scalar(select(Transaction).where(Transaction.transaction_id == "txn_1"))
    assert txn is not None  # row stays
    assert txn.removed_at is not None  # soft-delete


def test_apply_page_advances_cursor_and_last_sync_at(session, seeded_chain):
    page = _page(added=[_txn("txn_1")], next_cursor="cursor_xyz")
    before = datetime.utcnow()
    apply_sync_page(session, item_id=seeded_chain["item"].item_id, page=page)
    session.commit()

    item = session.scalar(select(Item).where(Item.item_id == seeded_chain["item"].item_id))
    assert item.transactions_cursor == "cursor_xyz"
    assert item.last_sync_at is not None
    assert item.last_sync_at >= before


# ---------- atomicity --------------------------------------------------------


def test_failure_mid_apply_does_not_advance_cursor(session, seeded_chain):
    """If apply_sync_page raises, the caller's transaction rolls back: no cursor change."""
    # Two adds: the first is fine; the second references a non-existent account, so
    # the FK insert will fail at flush/commit. We expect:
    #  - The caller's session.commit() raises.
    #  - The cursor remains None (its initial value).
    #  - Neither transaction is committed.
    item_id = seeded_chain["item"].item_id

    bad_page = _page(
        added=[
            _txn("txn_good", account_id="acc_test"),
            _txn("txn_bad", account_id="acc_does_not_exist"),
        ],
        next_cursor="should_not_persist",
    )
    apply_sync_page(session, item_id=item_id, page=bad_page)
    with pytest.raises(Exception):
        session.commit()
    session.rollback()

    item = session.scalar(select(Item).where(Item.item_id == item_id))
    assert item.transactions_cursor is None
    assert session.scalar(select(Transaction)) is None


def test_replaying_a_page_is_idempotent(session, seeded_chain):
    """Apply the same page twice — end state identical to applying once."""
    item_id = seeded_chain["item"].item_id
    page = _page(added=[_txn("txn_1", amount=42.0)])

    apply_sync_page(session, item_id=item_id, page=page)
    session.commit()
    apply_sync_page(session, item_id=item_id, page=page)
    session.commit()

    txns = session.scalars(select(Transaction)).all()
    assert len(txns) == 1
    assert txns[0].amount == 42.0


# ---------- per-item isolation -----------------------------------------------


def test_apply_for_one_item_does_not_touch_another_item(session, seeded_chain):
    """Adding a second item + transactions should not affect the first item's cursor."""
    from core.db import Account, Item

    other = Item(
        item_id="item_other",
        institution_id="ins_test",
        access_token_ciphertext=b"\x00" * 28,
        transactions_cursor="other_existing_cursor",
    )
    other_acct = Account(
        account_id="acc_other",
        item_id="item_other",
        name="Other Checking",
        type="depository",
        subtype="checking",
    )
    session.add_all([other, other_acct])
    session.commit()

    page = _page(
        added=[_txn("txn_for_other", account_id="acc_other")],
        next_cursor="new_first_cursor",
    )
    apply_sync_page(session, item_id="item_other", page=page)
    session.commit()

    first_item = session.scalar(select(Item).where(Item.item_id == seeded_chain["item"].item_id))
    other_item = session.scalar(select(Item).where(Item.item_id == "item_other"))
    assert first_item.transactions_cursor is None
    assert other_item.transactions_cursor == "new_first_cursor"
