from datetime import date

from core.queries.categories import category_spend


def test_category_spend_groups_by_primary_category(session, queries_seed):
    """In the seeded date range, FOOD_AND_DRINK has 3 txns summing to 164.75
    (42.50 + 37.25 + 85.00); TRANSPORTATION has 1 (55.00); INCOME has -3000.
    Income is excluded from spend by default (positive amounts only)."""
    result = category_spend(session, start_date=date(2026, 4, 1), end_date=date(2026, 4, 30))
    by_cat = {row["category_primary"]: row["total"] for row in result}
    assert by_cat["FOOD_AND_DRINK"] == 42.50 + 37.25 + 85.00
    assert by_cat["TRANSPORTATION"] == 55.00
    # INCOME excluded (negative amounts skipped).
    assert "INCOME" not in by_cat


def test_category_spend_excludes_removed_rows(session, queries_seed):
    """txn_removed (GENERAL_MERCHANDISE, removed_at set) should not appear."""
    result = category_spend(session, start_date=date(2026, 4, 1), end_date=date(2026, 4, 30))
    cats = {row["category_primary"] for row in result}
    assert "GENERAL_MERCHANDISE" not in cats


def test_category_spend_returns_count_per_category(session, queries_seed):
    result = category_spend(session, start_date=date(2026, 4, 1), end_date=date(2026, 4, 30))
    by_cat_count = {row["category_primary"]: row["count"] for row in result}
    assert by_cat_count["FOOD_AND_DRINK"] == 3
    assert by_cat_count["TRANSPORTATION"] == 1


def test_category_spend_empty_range(session, queries_seed):
    """Date range with no transactions — empty list."""
    result = category_spend(session, start_date=date(2099, 1, 1), end_date=date(2099, 12, 31))
    assert result == []


def test_category_spend_sorted_by_total_desc(session, queries_seed):
    """Highest spend first."""
    result = category_spend(session, start_date=date(2026, 4, 1), end_date=date(2026, 4, 30))
    totals = [row["total"] for row in result]
    assert totals == sorted(totals, reverse=True)
