"""Transactions sync engine.

This module implements the cursor-atomicity invariant from spec section 7.3:
the cursor advances if and only if every row in the page is persisted.
The caller is responsible for the surrounding `session.commit()` so the cursor
write and the row writes share a single SQL transaction.
"""
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import Item, Transaction


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_date(value: Any) -> date | None:
    """Plaid returns ISO date strings; sometimes datetime.date instances."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise TypeError(f"Cannot parse date from {value!r}")


def _txn_columns_from_payload(item_id: str, payload: dict) -> dict:
    """Map a Plaid transaction dict → keyword args for the Transaction model."""
    pfc = payload.get("personal_finance_category") or {}
    return {
        "transaction_id": payload["transaction_id"],
        "account_id": payload["account_id"],
        "date": _parse_date(payload.get("date")),
        "authorized_date": _parse_date(payload.get("authorized_date")),
        "amount": float(payload.get("amount", 0.0)),
        "iso_currency_code": payload.get("iso_currency_code"),
        "name": payload.get("name") or "",
        "merchant_name": payload.get("merchant_name"),
        "payment_channel": payload.get("payment_channel"),
        "pending": bool(payload.get("pending", False)),
        "category_primary": pfc.get("primary"),
        "category_detailed": pfc.get("detailed"),
        "category_confidence": pfc.get("confidence_level"),
        "raw_payload": payload,
    }


def apply_sync_page(session: Session, *, item_id: str, page: Any) -> None:
    """Apply a single page from /transactions/sync.

    `page` must have attributes: `added` (list of dicts), `modified` (list of dicts),
    `removed` (list of dicts each with `transaction_id`), `has_more` (bool),
    `next_cursor` (str). plaid-python's response object satisfies this; tests can
    pass a SimpleNamespace.

    DOES NOT call session.commit() — the caller is responsible. This lets the
    cursor write share an SQL transaction with the row writes (atomicity).
    """
    item = session.scalar(select(Item).where(Item.item_id == item_id))
    if item is None:
        raise LookupError(f"Item not found: {item_id}")

    now = _utcnow_naive()

    # 1. Added: insert as new rows, or revive a soft-deleted row if the same id exists.
    for payload in page.added:
        cols = _txn_columns_from_payload(item_id, payload)
        existing = session.scalar(
            select(Transaction).where(Transaction.transaction_id == cols["transaction_id"])
        )
        if existing is None:
            session.add(Transaction(**cols, created_at=now, updated_at=now))
        else:
            # Idempotent replay: if a previous run added this txn, just update.
            for k, v in cols.items():
                setattr(existing, k, v)
            existing.removed_at = None
            existing.updated_at = now

    # 2. Modified: same as added but the row is expected to exist.
    for payload in page.modified:
        cols = _txn_columns_from_payload(item_id, payload)
        existing = session.scalar(
            select(Transaction).where(Transaction.transaction_id == cols["transaction_id"])
        )
        if existing is None:
            # Plaid sent a "modified" for a row we don't have — treat as added.
            session.add(Transaction(**cols, created_at=now, updated_at=now))
        else:
            for k, v in cols.items():
                setattr(existing, k, v)
            existing.updated_at = now

    # 3. Removed: soft-delete (preserve the row).
    for payload in page.removed:
        existing = session.scalar(
            select(Transaction).where(Transaction.transaction_id == payload["transaction_id"])
        )
        if existing is not None and existing.removed_at is None:
            existing.removed_at = now
            existing.updated_at = now

    # 4. Advance cursor + sync timestamp on the Item row, in the same SQL transaction.
    item.transactions_cursor = page.next_cursor
    item.last_sync_at = now
