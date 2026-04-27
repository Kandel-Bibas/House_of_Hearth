"""list_accounts — accounts joined with their Item and Institution for UI display."""
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import Account, Institution, Item


def list_accounts(session: Session) -> list[dict[str, Any]]:
    """Return all accounts with institution name and last-sync status from their Item."""
    stmt = (
        select(Account, Item, Institution)
        .join(Item, Item.item_id == Account.item_id)
        .join(Institution, Institution.institution_id == Item.institution_id)
        .order_by(Institution.name, Account.name)
    )
    rows = session.execute(stmt).all()
    return [
        {
            "account_id": a.account_id,
            "name": a.name,
            "official_name": a.official_name,
            "type": a.type,
            "subtype": a.subtype,
            "mask": a.mask,
            "current_balance": a.current_balance,
            "available_balance": a.available_balance,
            "limit_balance": a.limit_balance,
            "iso_currency_code": a.iso_currency_code,
            "last_balance_at": a.last_balance_at.isoformat() if a.last_balance_at else None,
            "item_id": i.item_id,
            "institution_id": inst.institution_id,
            "institution_name": inst.name,
            "institution_logo": inst.logo,
            "institution_primary_color": inst.primary_color,
            "last_sync_status": i.last_sync_status,
            "last_sync_error": i.last_sync_error,
            "last_sync_at": i.last_sync_at.isoformat() if i.last_sync_at else None,
        }
        for a, i, inst in rows
    ]
