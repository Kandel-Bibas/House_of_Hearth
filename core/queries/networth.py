"""net_worth — sum of account balances, signed by account type.

Returns:
    {
        "total": float,
        "depository": float,
        "credit": float,         # raw sum (Plaid convention: positive = owed)
        "investment": float,
        "loan": float,
    }

Sign convention for `total`:
    total = depository + investment - credit - loan
"""
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.db import Account


def net_worth(session: Session) -> dict[str, Any]:
    """Compute net worth across all accounts."""
    stmt = (
        select(Account.type, func.coalesce(func.sum(Account.current_balance), 0.0))
        .group_by(Account.type)
    )
    by_type = {row[0]: float(row[1]) for row in session.execute(stmt).all()}

    depository = by_type.get("depository", 0.0)
    credit = by_type.get("credit", 0.0)
    investment = by_type.get("investment", 0.0)
    loan = by_type.get("loan", 0.0)

    return {
        "total": depository + investment - credit - loan,
        "depository": depository,
        "credit": credit,
        "investment": investment,
        "loan": loan,
    }
