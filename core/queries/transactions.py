"""search_transactions — filtered, soft-delete-aware transaction list.

Returns JSON-safe dicts (date → ISO string, no SQLAlchemy objects).
"""
from datetime import date as date_t
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import Transaction


def _row_to_dict(t: Transaction) -> dict[str, Any]:
    return {
        "transaction_id": t.transaction_id,
        "account_id": t.account_id,
        "date": t.date.isoformat() if t.date else None,
        "authorized_date": t.authorized_date.isoformat() if t.authorized_date else None,
        "amount": t.amount,
        "iso_currency_code": t.iso_currency_code,
        "name": t.name,
        "merchant_name": t.merchant_name,
        "payment_channel": t.payment_channel,
        "pending": t.pending,
        "category_primary": t.category_primary,
        "category_detailed": t.category_detailed,
        "category_confidence": t.category_confidence,
        "removed_at": t.removed_at.isoformat() if t.removed_at else None,
    }


def search_transactions(
    session: Session,
    *,
    start_date: Optional[date_t] = None,
    end_date: Optional[date_t] = None,
    account_id: Optional[str] = None,
    category_primary: Optional[str] = None,
    category_detailed: Optional[str] = None,
    merchant_name: Optional[str] = None,        # substring, case-insensitive
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    include_removed: bool = False,
    limit: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Return matching transactions as JSON-safe dicts, newest first.

    Defaults: excludes soft-deleted rows (removed_at IS NULL). Pass
    `include_removed=True` to include them.
    """
    stmt = select(Transaction)

    if not include_removed:
        stmt = stmt.where(Transaction.removed_at.is_(None))
    if start_date is not None:
        stmt = stmt.where(Transaction.date >= start_date)
    if end_date is not None:
        stmt = stmt.where(Transaction.date <= end_date)
    if account_id is not None:
        stmt = stmt.where(Transaction.account_id == account_id)
    if category_primary is not None:
        stmt = stmt.where(Transaction.category_primary == category_primary)
    if category_detailed is not None:
        stmt = stmt.where(Transaction.category_detailed == category_detailed)
    if merchant_name is not None:
        # SQLite LIKE is case-insensitive for ASCII by default.
        stmt = stmt.where(Transaction.merchant_name.ilike(f"%{merchant_name}%"))
    if min_amount is not None:
        stmt = stmt.where(Transaction.amount >= min_amount)
    if max_amount is not None:
        stmt = stmt.where(Transaction.amount <= max_amount)

    stmt = stmt.order_by(Transaction.date.desc(), Transaction.transaction_id.desc())
    if limit is not None:
        stmt = stmt.limit(limit)

    rows = session.scalars(stmt).all()
    return [_row_to_dict(t) for t in rows]
