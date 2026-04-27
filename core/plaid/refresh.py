"""Balance + holdings refresh.

- refresh_balances: /accounts/get → overwrite Account balance columns.
- refresh_holdings: /investments/holdings/get → upsert Securities, overwrite Holdings,
                    refresh investment Account balances.

Both functions commit the session.
"""
from datetime import date, datetime, timezone
from typing import Any

from plaid.api.plaid_api import PlaidApi
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.investments_holdings_get_request import InvestmentsHoldingsGetRequest
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import Account, Holding, Security


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise TypeError(f"Cannot parse date from {value!r}")


def _apply_account_payload(session: Session, item_id: str, acct_payload: dict, now: datetime) -> None:
    """Upsert one account row from a Plaid account-shaped payload."""
    balances = acct_payload.get("balances") or {}
    existing = session.scalar(
        select(Account).where(Account.account_id == acct_payload["account_id"])
    )
    cols = {
        "name": acct_payload.get("name") or "",
        "official_name": acct_payload.get("official_name"),
        "type": str(acct_payload.get("type")),
        "subtype": str(acct_payload.get("subtype")) if acct_payload.get("subtype") else None,
        "mask": acct_payload.get("mask"),
        "current_balance": balances.get("current"),
        "available_balance": balances.get("available"),
        "limit_balance": balances.get("limit"),
        "iso_currency_code": balances.get("iso_currency_code"),
        "last_balance_at": now,
        "raw_payload": acct_payload,
    }
    if existing is None:
        session.add(
            Account(
                account_id=acct_payload["account_id"],
                item_id=item_id,
                **cols,
            )
        )
    else:
        for k, v in cols.items():
            setattr(existing, k, v)


def has_investment_accounts(session: Session, *, item_id: str) -> bool:
    """True iff this Item has at least one account where type == 'investment'."""
    result = session.scalar(
        select(Account).where(Account.item_id == item_id, Account.type == "investment")
    )
    return result is not None


def refresh_balances(
    *,
    client: PlaidApi,
    session: Session,
    item_id: str,
    access_token: str,
) -> None:
    """Call /accounts/get and overwrite balance columns for every account in this Item."""
    response = client.accounts_get(AccountsGetRequest(access_token=access_token))
    payload = response.to_dict()
    now = _utcnow_naive()
    for acct_payload in payload["accounts"]:
        _apply_account_payload(session, item_id, acct_payload, now)
    session.commit()


def refresh_holdings(
    *,
    client: PlaidApi,
    session: Session,
    item_id: str,
    access_token: str,
) -> None:
    """Call /investments/holdings/get; upsert securities, overwrite holdings, refresh
    investment-account balances. Caller is responsible for only invoking this when
    has_investment_accounts(session, item_id=...) is True."""
    response = client.investments_holdings_get(
        InvestmentsHoldingsGetRequest(access_token=access_token)
    )
    payload = response.to_dict()
    now = _utcnow_naive()

    # 1. Upsert securities.
    for sec_payload in payload.get("securities", []):
        existing = session.scalar(
            select(Security).where(Security.security_id == sec_payload["security_id"])
        )
        cols = {
            "ticker_symbol": sec_payload.get("ticker_symbol"),
            "name": sec_payload.get("name"),
            "type": sec_payload.get("type"),
            "iso_currency_code": sec_payload.get("iso_currency_code"),
            "close_price": sec_payload.get("close_price"),
            "close_price_as_of": _parse_date(sec_payload.get("close_price_as_of")),
        }
        if existing is None:
            session.add(Security(security_id=sec_payload["security_id"], **cols))
        else:
            for k, v in cols.items():
                setattr(existing, k, v)

    # 2. Refresh balances on the accounts in this response (investment accts).
    for acct_payload in payload.get("accounts", []):
        _apply_account_payload(session, item_id, acct_payload, now)

    # 3. Overwrite holdings: delete existing holdings for these accounts, insert fresh.
    affected_account_ids = {h["account_id"] for h in payload.get("holdings", [])}
    if affected_account_ids:
        existing_holdings = session.scalars(
            select(Holding).where(Holding.account_id.in_(affected_account_ids))
        ).all()
        for h in existing_holdings:
            session.delete(h)
        session.flush()

    for h_payload in payload.get("holdings", []):
        session.add(
            Holding(
                account_id=h_payload["account_id"],
                security_id=h_payload["security_id"],
                quantity=float(h_payload.get("quantity", 0.0)),
                institution_price=h_payload.get("institution_price"),
                institution_value=h_payload.get("institution_value"),
                cost_basis=h_payload.get("cost_basis"),
                last_synced_at=now,
            )
        )

    session.commit()
