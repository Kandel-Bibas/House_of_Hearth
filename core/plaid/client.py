"""Plaid client factory — env-aware wrapper around plaid-python's PlaidApi.

Usage:
    from core.plaid.client import PlaidEnv, make_plaid_client
    client = make_plaid_client(
        env=PlaidEnv.SANDBOX,
        client_id=os.environ["PLAID_CLIENT_ID"],
        secret=os.environ["PLAID_SECRET"],
    )
    response = client.link_token_create(request)
"""
from enum import Enum

import plaid
from plaid.api import plaid_api


class PlaidEnv(str, Enum):
    """Plaid environments. The user's Development env is what the app uses in production."""

    SANDBOX = "sandbox"
    DEVELOPMENT = "development"
    PRODUCTION = "production"


# plaid-python >= 31 dropped `plaid.Environment.Development` (Plaid deprecated
# the Development tier in their public API), so we fall back to literal URLs.
_HOSTS: dict[PlaidEnv, str] = {
    PlaidEnv.SANDBOX: "https://sandbox.plaid.com",
    PlaidEnv.DEVELOPMENT: "https://development.plaid.com",
    PlaidEnv.PRODUCTION: "https://production.plaid.com",
}


def make_plaid_client(
    *, env: PlaidEnv, client_id: str, secret: str
) -> plaid_api.PlaidApi:
    """Create a configured PlaidApi instance for the given environment."""
    configuration = plaid.Configuration(
        host=_HOSTS[env],
        api_key={
            "clientId": client_id,
            "secret": secret,
        },
    )
    api_client = plaid.ApiClient(configuration)
    return plaid_api.PlaidApi(api_client)
