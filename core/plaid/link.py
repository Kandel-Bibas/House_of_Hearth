"""Plaid Link flow: create link_token, exchange public_token → access_token, persist Item.

The Link iframe runs in the user's browser (frontend) and posts the public_token
to our /plaid/exchange endpoint, which calls exchange_public_token here.

Public API:
- create_link_token(client, *, client_user_id) -> str
- exchange_public_token(client, session, *, public_token) -> str  (returns item_id)
"""
from datetime import datetime, timezone
from typing import Any

from plaid.api.plaid_api import PlaidApi
from plaid.model.country_code import CountryCode
from plaid.model.institutions_get_by_id_request import InstitutionsGetByIdRequest
from plaid.model.item_public_token_exchange_request import (
    ItemPublicTokenExchangeRequest,
)
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products
from plaid.model.accounts_get_request import AccountsGetRequest
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import Account, Institution, Item
from core.plaid.tokens import store_encrypted_token


_PRODUCTS = [Products("transactions"), Products("investments")]
_COUNTRY_CODES = [CountryCode("US")]


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def create_link_token(client: PlaidApi, *, client_user_id: str) -> str:
    """Ask Plaid for a short-lived Link token. The frontend uses it to open the iframe."""
    request = LinkTokenCreateRequest(
        products=_PRODUCTS,
        client_name="Finance Tracker",
        country_codes=_COUNTRY_CODES,
        language="en",
        user=LinkTokenCreateRequestUser(client_user_id=client_user_id),
    )
    response = client.link_token_create(request)
    return response.link_token


def exchange_public_token(
    client: PlaidApi,
    session: Session,
    *,
    public_token: str,
) -> str:
    """Exchange a short-lived public_token for a long-lived access_token, encrypt it,
    and persist the Item, Institution, and initial Accounts. Returns item_id.

    The session is committed only after every row is written. On any failure mid-way,
    nothing is persisted.
    """
    # 1. public_token → access_token + item_id
    exchange_resp = client.item_public_token_exchange(
        ItemPublicTokenExchangeRequest(public_token=public_token)
    )
    access_token = exchange_resp.access_token
    item_id = exchange_resp.item_id

    # 2. /accounts/get → institution_id + initial accounts
    accounts_resp = client.accounts_get(AccountsGetRequest(access_token=access_token))
    accounts_resp_dict = accounts_resp.to_dict()
    institution_id = accounts_resp_dict["item"]["institution_id"]
    accounts_payload = accounts_resp_dict["accounts"]

    # 3. Upsert Institution (lookup if missing).
    inst = session.scalar(
        select(Institution).where(Institution.institution_id == institution_id)
    )
    if inst is None:
        inst = _fetch_and_build_institution(client, institution_id)
        session.add(inst)

    # 4. Insert Item with placeholder ciphertext (we'll overwrite after add).
    now = _utcnow_naive()
    item = Item(
        item_id=item_id,
        institution_id=institution_id,
        access_token_ciphertext=b"\x00" * 28,  # placeholder, replaced below
        last_sync_at=None,
        last_sync_status="pending",
        last_sync_error=None,
        created_at=now,
    )
    session.add(item)
    session.flush()  # so the Item is queryable by store_encrypted_token

    # 5. Encrypt the access token onto the just-inserted Item row.
    store_encrypted_token(session, item_id=item_id, access_token=access_token)

    # 6. Insert all accounts.
    for acct_payload in accounts_payload:
        balances = acct_payload.get("balances") or {}
        session.add(
            Account(
                account_id=acct_payload["account_id"],
                item_id=item_id,
                name=acct_payload.get("name") or "",
                official_name=acct_payload.get("official_name"),
                type=str(acct_payload.get("type")),
                subtype=str(acct_payload.get("subtype")) if acct_payload.get("subtype") else None,
                mask=acct_payload.get("mask"),
                current_balance=balances.get("current"),
                available_balance=balances.get("available"),
                limit_balance=balances.get("limit"),
                iso_currency_code=balances.get("iso_currency_code"),
                last_balance_at=now,
                raw_payload=acct_payload,
            )
        )

    session.commit()
    return item_id


def _fetch_and_build_institution(client: PlaidApi, institution_id: str) -> Institution:
    """Call /institutions/get_by_id and shape the response into an Institution row."""
    resp = client.institutions_get_by_id(
        InstitutionsGetByIdRequest(
            institution_id=institution_id,
            country_codes=_COUNTRY_CODES,
        )
    )
    payload: dict[str, Any] = resp.to_dict()["institution"]
    return Institution(
        institution_id=payload["institution_id"],
        name=payload.get("name") or "",
        logo=payload.get("logo"),
        primary_color=payload.get("primary_color"),
        url=payload.get("url"),
    )
