from datetime import date

from core.queries.transactions import search_transactions


def test_returns_all_non_removed_by_default(session, queries_seed):
    """No filters → all 5 non-removed transactions, newest first."""
    results = search_transactions(session)
    assert len(results) == 5
    # The seeded `txn_removed` (date 2026-04-08, removed_at set) is excluded.
    assert all(r["transaction_id"] != "txn_removed" for r in results)
    # Default sort: date desc.
    dates = [r["date"] for r in results]
    assert dates == sorted(dates, reverse=True)


def test_returns_dicts_not_orm_objects(session, queries_seed):
    """Result rows are JSON-safe dicts, not SQLAlchemy objects."""
    results = search_transactions(session)
    assert isinstance(results, list)
    assert isinstance(results[0], dict)
    # date should be ISO string for JSON-safety, not datetime.date.
    assert isinstance(results[0]["date"], str)


def test_filters_by_date_range(session, queries_seed):
    """Inclusive on both ends."""
    results = search_transactions(session, start_date=date(2026, 4, 5), end_date=date(2026, 4, 12))
    ids = {r["transaction_id"] for r in results}
    assert ids == {"txn_restaurant_1", "txn_grocery_2", "txn_gas_1"}


def test_filters_by_category_primary(session, queries_seed):
    results = search_transactions(session, category_primary="FOOD_AND_DRINK")
    ids = {r["transaction_id"] for r in results}
    assert ids == {"txn_grocery_1", "txn_grocery_2", "txn_restaurant_1"}


def test_filters_by_merchant_name_substring(session, queries_seed):
    """Substring match, case-insensitive."""
    results = search_transactions(session, merchant_name="whole")
    ids = {r["transaction_id"] for r in results}
    assert ids == {"txn_grocery_1"}


def test_filters_by_account_id(session, queries_seed):
    results = search_transactions(session, account_id="acc_credit")
    ids = {r["transaction_id"] for r in results}
    assert ids == {"txn_gas_1"}


def test_filters_by_min_max_amount(session, queries_seed):
    """Amount filters work over outflows; negatives (income) are below 0."""
    results = search_transactions(session, min_amount=50.0, max_amount=90.0)
    ids = {r["transaction_id"] for r in results}
    assert ids == {"txn_restaurant_1", "txn_gas_1"}


def test_include_removed_returns_soft_deleted_too(session, queries_seed):
    results = search_transactions(session, include_removed=True)
    ids = {r["transaction_id"] for r in results}
    assert "txn_removed" in ids


def test_limit_truncates_results(session, queries_seed):
    results = search_transactions(session, limit=2)
    assert len(results) == 2


def test_combined_filters(session, queries_seed):
    """Date + category + min_amount in one call."""
    # NOTE: end_date adjusted from plan's 2026-04-10 to 2026-04-03 to make
    # the assertion `ids == {"txn_grocery_1"}` actually hold. With end=4/10,
    # txn_restaurant_1 (4/5, 85.00, FOOD_AND_DRINK) also matches min_amount=40.
    # The narrower end_date isolates grocery_1 (4/1) from restaurant_1 (4/5).
    results = search_transactions(
        session,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 3),
        category_primary="FOOD_AND_DRINK",
        min_amount=40.0,
    )
    ids = {r["transaction_id"] for r in results}
    assert ids == {"txn_grocery_1"}
