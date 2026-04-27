"""Transactions sync engine.

This module implements the cursor-atomicity invariant from spec section 7.3:
the cursor advances if and only if every row in the page is persisted.
The caller is responsible for the surrounding `session.commit()` so the cursor
write and the row writes share a single SQL transaction.
"""
import json
import time
from datetime import date, datetime, timezone
from typing import Any

from plaid.api.plaid_api import PlaidApi
from plaid.exceptions import ApiException
from plaid.model.transactions_sync_request import TransactionsSyncRequest
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import Item, Transaction
from core.plaid.errors import classify_plaid_error, is_retryable


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _maybe_to_dict(obj: Any) -> Any:
    """Convert plaid-python model objects to plain dicts; pass through if already a dict."""
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    return obj


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


_RETRY_DELAYS_SECONDS = [1, 2, 4, 8, 16]  # exponential backoff for retryable errors


def _extract_error_code_and_message(exc: ApiException) -> tuple[str, str]:
    """Pull error_code / error_message out of the JSON body Plaid returns on errors."""
    try:
        body = json.loads(exc.body) if isinstance(exc.body, str) else (exc.body or {})
    except (ValueError, TypeError):
        body = {}
    return body.get("error_code", "UNKNOWN_ERROR"), body.get("error_message", str(exc))


def sync_transactions(
    *,
    client: PlaidApi,
    session: Session,
    item_id: str,
    access_token: str,
) -> None:
    """Drive /transactions/sync to has_more=False, applying each page atomically.

    On retryable Plaid errors (PRODUCT_NOT_READY, RATE_LIMIT_EXCEEDED, INSTITUTION_*),
    backs off exponentially and retries the same page. On non-retryable errors,
    classifies, writes status='error' to the Item, and re-raises.
    """
    item = session.scalar(select(Item).where(Item.item_id == item_id))
    if item is None:
        raise LookupError(f"Item not found: {item_id}")

    cursor = item.transactions_cursor

    while True:
        request = TransactionsSyncRequest(
            access_token=access_token,
            cursor=cursor or "",
        )
        try:
            response = _call_with_retries(client.transactions_sync, request)
        except ApiException as exc:
            code, msg = _extract_error_code_and_message(exc)
            outcome = classify_plaid_error(code, msg)
            item.last_sync_status = outcome.status
            item.last_sync_error = outcome.error
            session.commit()
            raise

        # plaid-python returns model objects (Transaction, RemovedTransaction, ...).
        # Convert to plain dicts so they JSON-serialize when stored in raw_payload.
        # Tests pass dicts directly; pass-through in that case.
        from types import SimpleNamespace
        page = SimpleNamespace(
            added=[_maybe_to_dict(t) for t in response.added],
            modified=[_maybe_to_dict(t) for t in response.modified],
            removed=[_maybe_to_dict(r) for r in response.removed],
            has_more=response.has_more,
            next_cursor=response.next_cursor,
        )
        apply_sync_page(session, item_id=item_id, page=page)
        # Each page commits independently — a 500-page Item that fails on page 487
        # keeps pages 1-486 committed and resumes at 487 next run.
        session.commit()

        cursor = page.next_cursor
        if not page.has_more:
            break

    item.last_sync_status = "ok"
    item.last_sync_error = None
    session.commit()


def _call_with_retries(api_call, request) -> Any:
    """Call a Plaid API method with exponential backoff on retryable errors.

    Raises the final ApiException if retries are exhausted, or any non-retryable
    error on first occurrence.
    """
    delays = list(_RETRY_DELAYS_SECONDS)
    while True:
        try:
            return api_call(request)
        except ApiException as exc:
            code, _ = _extract_error_code_and_message(exc)
            if not is_retryable(code) or not delays:
                raise
            time.sleep(delays.pop(0))
