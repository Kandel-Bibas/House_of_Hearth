"""category_spend — outflow grouped by personal_finance_category.primary.

Excludes inflows (negative amounts, per Plaid convention) and soft-deleted txns.
"""
from datetime import date as date_t
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from core.db import Transaction


def category_spend(
    session: Session,
    *,
    start_date: date_t,
    end_date: date_t,
) -> list[dict[str, Any]]:
    """Sum outflows by category over [start_date, end_date] inclusive.

    Returns: list of {"category_primary": str, "total": float, "count": int},
    sorted by total descending. Inflows (amount < 0) and soft-deleted rows are excluded.
    Categories with NULL primary are aggregated under "UNCATEGORIZED".
    """
    cat_expr = func.coalesce(Transaction.category_primary, "UNCATEGORIZED")
    stmt = (
        select(
            cat_expr.label("category_primary"),
            func.sum(Transaction.amount).label("total"),
            func.count(Transaction.transaction_id).label("count"),
        )
        .where(Transaction.removed_at.is_(None))
        .where(Transaction.date >= start_date)
        .where(Transaction.date <= end_date)
        .where(Transaction.amount > 0)
        .group_by(cat_expr)
        .order_by(func.sum(Transaction.amount).desc())
    )
    rows = session.execute(stmt).all()
    return [
        {"category_primary": r.category_primary, "total": float(r.total), "count": int(r.count)}
        for r in rows
    ]
