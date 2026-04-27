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


# ============================================================================
# sync_transactions (multi-page) tests
# ============================================================================
from unittest.mock import MagicMock

from core.plaid.sync import sync_transactions
from plaid.exceptions import ApiException


def _wrap_page(payload: dict) -> MagicMock:
    obj = MagicMock()
    obj.to_dict.return_value = payload
    for key, value in payload.items():
        setattr(obj, key, value)
    return obj


def test_sync_transactions_loops_until_has_more_false(
    session, seeded_chain, fake_plaid_client
):
    """Three-page response — all 3 pages applied, final cursor is the last next_cursor."""
    fake_plaid_client.transactions_sync.side_effect = [
        _wrap_page(
            {
                "added": [_txn("p1_txn1")],
                "modified": [],
                "removed": [],
                "has_more": True,
                "next_cursor": "c1",
            }
        ),
        _wrap_page(
            {
                "added": [_txn("p2_txn1"), _txn("p2_txn2")],
                "modified": [],
                "removed": [],
                "has_more": True,
                "next_cursor": "c2",
            }
        ),
        _wrap_page(
            {
                "added": [_txn("p3_txn1")],
                "modified": [],
                "removed": [],
                "has_more": False,
                "next_cursor": "c3_final",
            }
        ),
    ]

    sync_transactions(
        client=fake_plaid_client,
        session=session,
        item_id=seeded_chain["item"].item_id,
        access_token="access-sandbox-xyz",
    )

    txns = session.scalars(select(Transaction)).all()
    assert {t.transaction_id for t in txns} == {"p1_txn1", "p2_txn1", "p2_txn2", "p3_txn1"}

    item = session.scalar(select(Item).where(Item.item_id == seeded_chain["item"].item_id))
    assert item.transactions_cursor == "c3_final"
    assert item.last_sync_status == "ok"
    assert item.last_sync_error is None


def test_sync_transactions_passes_cursor_from_item_on_first_call(
    session, seeded_chain, fake_plaid_client
):
    """If the Item already has a cursor, /transactions/sync is called with it."""
    item = seeded_chain["item"]
    item.transactions_cursor = "saved_cursor_from_last_run"
    session.commit()

    fake_plaid_client.transactions_sync.return_value = _wrap_page(
        {
            "added": [],
            "modified": [],
            "removed": [],
            "has_more": False,
            "next_cursor": "saved_cursor_from_last_run",
        }
    )

    sync_transactions(
        client=fake_plaid_client,
        session=session,
        item_id=item.item_id,
        access_token="access-sandbox-xyz",
    )

    # The first call's request body included the saved cursor.
    first_call = fake_plaid_client.transactions_sync.call_args_list[0]
    request = first_call.args[0]
    # The plaid request object exposes .cursor as an attr.
    assert request.cursor == "saved_cursor_from_last_run"


def test_sync_transactions_classifies_plaid_error_and_does_not_advance(
    session, seeded_chain, fake_plaid_client
):
    """A Plaid ApiException for a non-retryable code marks the Item error and re-raises."""
    api_exc = ApiException(status=400)
    api_exc.body = '{"error_code": "ITEM_LOGIN_REQUIRED", "error_message": "relink please"}'
    fake_plaid_client.transactions_sync.side_effect = api_exc

    with pytest.raises(ApiException):
        sync_transactions(
            client=fake_plaid_client,
            session=session,
            item_id=seeded_chain["item"].item_id,
            access_token="access-sandbox-xyz",
        )

    # The implementation should have committed the error status before re-raising.
    session.expire_all()
    item = session.scalar(select(Item).where(Item.item_id == seeded_chain["item"].item_id))
    assert item.last_sync_status == "error"
    assert "ITEM_LOGIN_REQUIRED" in (item.last_sync_error or "")


def test_sync_transactions_retries_product_not_ready(
    session, seeded_chain, fake_plaid_client, monkeypatch
):
    """PRODUCT_NOT_READY first → succeeds on retry. The monkeypatched sleep keeps the test fast."""
    api_exc = ApiException(status=400)
    api_exc.body = '{"error_code": "PRODUCT_NOT_READY", "error_message": "still backfilling"}'

    success_page = _wrap_page(
        {
            "added": [_txn("p1_txn1")],
            "modified": [],
            "removed": [],
            "has_more": False,
            "next_cursor": "c1",
        }
    )
    fake_plaid_client.transactions_sync.side_effect = [api_exc, success_page]

    # Don't actually sleep.
    monkeypatch.setattr("core.plaid.sync.time.sleep", lambda _seconds: None)

    sync_transactions(
        client=fake_plaid_client,
        session=session,
        item_id=seeded_chain["item"].item_id,
        access_token="access-sandbox-xyz",
    )

    item = session.scalar(select(Item).where(Item.item_id == seeded_chain["item"].item_id))
    assert item.last_sync_status == "ok"
    assert item.transactions_cursor == "c1"
