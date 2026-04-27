"""list_holdings — current investment positions joined with security + account metadata."""
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import Account, Holding, Security


def list_holdings(session: Session) -> list[dict[str, Any]]:
    """Return current holdings, joined with security and account metadata."""
    stmt = (
        select(Holding, Security, Account)
        .join(Security, Security.security_id == Holding.security_id)
        .join(Account, Account.account_id == Holding.account_id)
        .order_by(Account.account_id, Security.ticker_symbol)
    )
    rows = session.execute(stmt).all()
    return [
        {
            "account_id": h.account_id,
            "account_name": a.name,
            "security_id": h.security_id,
            "ticker_symbol": s.ticker_symbol,
            "security_name": s.name,
            "security_type": s.type,
            "quantity": h.quantity,
            "institution_price": h.institution_price,
            "institution_value": h.institution_value,
            "cost_basis": h.cost_basis,
            "iso_currency_code": s.iso_currency_code,
        }
        for h, s, a in rows
    ]
