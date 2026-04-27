import threading
from unittest.mock import MagicMock, call

import pytest
from sqlalchemy import select

from core.db import Account, Item, make_session_factory
from core.plaid.orchestrator import (
    PerItemLockRegistry,
    sync_all_items,
    sync_item,
)


def _make_session_factory(engine):
    return make_session_factory(engine)


def test_per_item_lock_registry_returns_same_lock_per_item_id():
    reg = PerItemLockRegistry()
    a1 = reg.lock_for("item_A")
    a2 = reg.lock_for("item_A")
    b = reg.lock_for("item_B")
    assert a1 is a2
    assert a1 is not b


def test_sync_item_marks_status_ok_on_success(
    engine, seeded_chain, fake_plaid_client, make_response, fake_keychain, monkeypatch
):
    """sync_item runs sync_transactions + refresh_balances; status='ok' afterwards."""
    # First, store a real ciphertext on the Item so decrypt works.
    SessionLocal = _make_session_factory(engine)
    with SessionLocal() as s:
        from core.plaid.tokens import store_encrypted_token
        store_encrypted_token(s, item_id="item_test", access_token="access-sandbox-xyz")
        s.commit()

    # transactions_sync: one empty page, has_more=False.
    fake_plaid_client.transactions_sync.return_value = make_response(
        {
            "added": [],
            "modified": [],
            "removed": [],
            "has_more": False,
            "next_cursor": "c_done",
        }
    )
    # accounts_get: refresh balance.
    fake_plaid_client.accounts_get.return_value = make_response(
        {
            "item": {"item_id": "item_test", "institution_id": "ins_test"},
            "accounts": [
                {
                    "account_id": "acc_test",
                    "name": "Checking",
                    "official_name": None,
                    "type": "depository",
                    "subtype": "checking",
                    "mask": "0000",
                    "balances": {
                        "current": 1234.56,
                        "available": 1234.56,
                        "limit": None,
                        "iso_currency_code": "USD",
                    },
                }
            ],
        }
    )

    sync_item(
        client_factory=lambda: fake_plaid_client,
        session_factory=SessionLocal,
        item_id="item_test",
    )

    with SessionLocal() as s:
        item = s.scalar(select(Item).where(Item.item_id == "item_test"))
        assert item.last_sync_status == "ok"
        assert item.transactions_cursor == "c_done"
        acct = s.scalar(select(Account).where(Account.account_id == "acc_test"))
        assert acct.current_balance == 1234.56

    # Investment-only call should NOT have happened (no investment account).
    fake_plaid_client.investments_holdings_get.assert_not_called()


def test_sync_item_skips_holdings_when_no_investment_account(
    engine, seeded_chain, fake_plaid_client, make_response, fake_keychain
):
    """has_investment_accounts is False → investments_holdings_get NOT called."""
    SessionLocal = _make_session_factory(engine)
    with SessionLocal() as s:
        from core.plaid.tokens import store_encrypted_token
        store_encrypted_token(s, item_id="item_test", access_token="access-sandbox-xyz")
        s.commit()

    fake_plaid_client.transactions_sync.return_value = make_response(
        {"added": [], "modified": [], "removed": [], "has_more": False, "next_cursor": "c"}
    )
    fake_plaid_client.accounts_get.return_value = make_response(
        {
            "item": {"item_id": "item_test", "institution_id": "ins_test"},
            "accounts": [],
        }
    )

    sync_item(
        client_factory=lambda: fake_plaid_client,
        session_factory=SessionLocal,
        item_id="item_test",
    )

    fake_plaid_client.investments_holdings_get.assert_not_called()


def test_sync_all_items_runs_each_in_parallel_isolated(
    engine, fake_keychain
):
    """Two Items, two fake clients — both run, both report ok, neither blocks the other."""
    SessionLocal = _make_session_factory(engine)
    # Seed two items + accounts + ciphertexts.
    with SessionLocal() as s:
        from core.db import Account, Institution, Item
        from core.plaid.tokens import store_encrypted_token
        s.add(Institution(institution_id="ins_X", name="X Bank"))
        for iid in ("item_X1", "item_X2"):
            s.add(Item(item_id=iid, institution_id="ins_X", access_token_ciphertext=b"\x00" * 28))
        s.add(Account(account_id="acc_X1", item_id="item_X1", name="A", type="depository"))
        s.add(Account(account_id="acc_X2", item_id="item_X2", name="B", type="depository"))
        s.flush()
        store_encrypted_token(s, item_id="item_X1", access_token="t1")
        store_encrypted_token(s, item_id="item_X2", access_token="t2")
        s.commit()

    def client_factory():
        c = MagicMock()
        c.transactions_sync.return_value = MagicMock(
            added=[],
            modified=[],
            removed=[],
            has_more=False,
            next_cursor="c",
            to_dict=lambda: {
                "added": [], "modified": [], "removed": [], "has_more": False, "next_cursor": "c",
            },
        )
        c.accounts_get.return_value = MagicMock(
            to_dict=lambda: {
                "item": {"item_id": "?", "institution_id": "ins_X"},
                "accounts": [],
            }
        )
        return c

    sync_all_items(
        client_factory=client_factory,
        session_factory=SessionLocal,
        item_ids=["item_X1", "item_X2"],
    )

    with SessionLocal() as s:
        items = s.scalars(select(Item).where(Item.item_id.in_(["item_X1", "item_X2"]))).all()
        assert all(i.last_sync_status == "ok" for i in items)


def test_sync_all_items_one_failure_does_not_block_others(
    engine, fake_keychain
):
    """One Item raises; the other still completes successfully."""
    SessionLocal = _make_session_factory(engine)
    with SessionLocal() as s:
        from core.db import Account, Institution, Item
        from core.plaid.tokens import store_encrypted_token
        s.add(Institution(institution_id="ins_X", name="X Bank"))
        s.add(Item(item_id="item_good", institution_id="ins_X", access_token_ciphertext=b"\x00" * 28))
        s.add(Item(item_id="item_bad", institution_id="ins_X", access_token_ciphertext=b"\x00" * 28))
        s.add(Account(account_id="acc_good", item_id="item_good", name="A", type="depository"))
        s.add(Account(account_id="acc_bad", item_id="item_bad", name="B", type="depository"))
        s.flush()
        store_encrypted_token(s, item_id="item_good", access_token="t_good")
        store_encrypted_token(s, item_id="item_bad", access_token="t_bad")
        s.commit()

    def client_factory():
        c = MagicMock()
        # Different per-call behavior depending on access_token in the request.
        def transactions_sync_side_effect(req):
            if req.access_token == "t_bad":
                raise RuntimeError("simulated network error")
            response = MagicMock()
            response.added = []
            response.modified = []
            response.removed = []
            response.has_more = False
            response.next_cursor = "c"
            return response

        c.transactions_sync.side_effect = transactions_sync_side_effect
        c.accounts_get.return_value = MagicMock(
            to_dict=lambda: {"item": {"item_id": "?", "institution_id": "ins_X"}, "accounts": []}
        )
        return c

    sync_all_items(
        client_factory=client_factory,
        session_factory=SessionLocal,
        item_ids=["item_good", "item_bad"],
    )

    with SessionLocal() as s:
        good = s.scalar(select(Item).where(Item.item_id == "item_good"))
        bad = s.scalar(select(Item).where(Item.item_id == "item_bad"))
        assert good.last_sync_status == "ok"
        assert bad.last_sync_status == "error"


def test_per_item_lock_serializes_overlapping_calls(
    engine, seeded_chain, fake_plaid_client, make_response, fake_keychain
):
    """Two threads calling sync_item for the same item_id — the second waits.

    Detected by counting transactions_sync calls and asserting they don't overlap.
    """
    SessionLocal = _make_session_factory(engine)
    with SessionLocal() as s:
        from core.plaid.tokens import store_encrypted_token
        store_encrypted_token(s, item_id="item_test", access_token="access-sandbox-xyz")
        s.commit()

    in_flight = threading.Event()
    can_finish = threading.Event()
    overlap_detected = []

    def slow_sync(req):
        # If we see this called while another call is in flight, that's an overlap.
        if in_flight.is_set():
            overlap_detected.append(True)
        in_flight.set()
        can_finish.wait(timeout=2)  # block until released
        in_flight.clear()
        response = MagicMock()
        response.added, response.modified, response.removed = [], [], []
        response.has_more = False
        response.next_cursor = "c"
        return response

    fake_plaid_client.transactions_sync.side_effect = slow_sync
    fake_plaid_client.accounts_get.return_value = make_response(
        {"item": {"item_id": "item_test", "institution_id": "ins_test"}, "accounts": []}
    )

    registry = PerItemLockRegistry()

    def call_sync():
        sync_item(
            client_factory=lambda: fake_plaid_client,
            session_factory=SessionLocal,
            item_id="item_test",
            lock_registry=registry,
        )

    t1 = threading.Thread(target=call_sync)
    t2 = threading.Thread(target=call_sync)
    t1.start()
    # Give t1 time to acquire the lock and start the slow_sync.
    in_flight.wait(timeout=1)
    t2.start()
    can_finish.set()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert overlap_detected == []  # the lock prevented overlap
