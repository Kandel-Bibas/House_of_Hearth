from core.queries.accounts import list_accounts


def test_list_accounts_returns_all_with_institution_metadata(session, queries_seed):
    rows = list_accounts(session)
    # 3 accounts in seed: acc_test, acc_credit, acc_invest
    assert len(rows) == 3
    by_id = {r["account_id"]: r for r in rows}
    assert by_id["acc_test"]["institution_name"] == "Test Bank"
    assert by_id["acc_test"]["type"] == "depository"
    assert by_id["acc_credit"]["type"] == "credit"
    assert by_id["acc_invest"]["type"] == "investment"


def test_list_accounts_includes_last_sync_status(session, queries_seed):
    """Item.last_sync_status / last_sync_error / last_sync_at are exposed per account."""
    from core.db import Item
    item = session.get(Item, "item_test")
    item.last_sync_status = "ok"
    session.commit()

    rows = list_accounts(session)
    for r in rows:
        assert r["last_sync_status"] == "ok"
        assert r["last_sync_error"] is None


def test_list_accounts_balances_present(session, queries_seed):
    rows = list_accounts(session)
    by_id = {r["account_id"]: r for r in rows}
    assert by_id["acc_test"]["current_balance"] == 1000.00
    assert by_id["acc_credit"]["limit_balance"] == 5000.00


def test_list_accounts_empty(session):
    """Empty DB → empty list."""
    assert list_accounts(session) == []
