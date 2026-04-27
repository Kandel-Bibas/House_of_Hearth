"""Plaid Sandbox integration ring — runs only with `pytest -m sandbox`.

Requires PLAID_CLIENT_ID and PLAID_SECRET in env (Plaid Sandbox credentials).
Free; deterministic data. Run with:

    PLAID_CLIENT_ID=<sandbox cid> PLAID_SECRET=<sandbox secret> \
      .venv/bin/pytest -m sandbox -v
"""
import os

import pytest
from plaid.model.country_code import CountryCode
from plaid.model.products import Products
from plaid.model.sandbox_public_token_create_request import (
    SandboxPublicTokenCreateRequest,
)
from sqlalchemy import select

from core.db import Item, Transaction, make_session_factory
from core.plaid import (
    PlaidEnv,
    exchange_public_token,
    make_plaid_client,
    sync_item,
)


# Skip the entire module unless PLAID_CLIENT_ID/SECRET are set.
pytestmark = [
    pytest.mark.sandbox,
    pytest.mark.skipif(
        not (os.environ.get("PLAID_CLIENT_ID") and os.environ.get("PLAID_SECRET")),
        reason="PLAID_CLIENT_ID and PLAID_SECRET must be set",
    ),
]


@pytest.fixture
def sandbox_client():
    return make_plaid_client(
        env=PlaidEnv.SANDBOX,
        client_id=os.environ["PLAID_CLIENT_ID"],
        secret=os.environ["PLAID_SECRET"],
    )


def _create_sandbox_public_token(client) -> str:
    """Use Plaid's sandbox-only endpoint to mint a public_token without UI."""
    resp = client.sandbox_public_token_create(
        SandboxPublicTokenCreateRequest(
            institution_id="ins_109508",  # Plaid's "First Platypus Bank" — always available
            initial_products=[Products("transactions")],
        )
    )
    return resp.public_token


def test_full_link_then_sync_against_sandbox(engine, fake_keychain, sandbox_client):
    """End-to-end: mint a sandbox public_token → exchange → sync_item → assert rows landed."""
    SessionLocal = make_session_factory(engine)

    public_token = _create_sandbox_public_token(sandbox_client)
    with SessionLocal() as s:
        item_id = exchange_public_token(
            client=sandbox_client, session=s, public_token=public_token
        )

    sync_item(
        client_factory=lambda: sandbox_client,
        session_factory=SessionLocal,
        item_id=item_id,
    )

    with SessionLocal() as s:
        item = s.scalar(select(Item).where(Item.item_id == item_id))
        assert item.last_sync_status == "ok", (item.last_sync_status, item.last_sync_error)
        # Sandbox accounts always have at least a few transactions.
        txns = s.scalars(select(Transaction)).all()
        assert len(txns) > 0
