"""Plaid-specific test fixtures — fake_client, canned response builders."""
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def fake_plaid_client():
    """A MagicMock standing in for plaid.api.plaid_api.PlaidApi.

    Each test sets up the methods it needs:
        fake_plaid_client.link_token_create.return_value = SomeResponse(...)

    The mock auto-attribute-generates every plaid-python method, so calling
    `fake_plaid_client.transactions_sync(req)` returns a MagicMock unless
    .return_value is set.
    """
    return MagicMock(name="fake_plaid_client")


def _wrap(payload: dict) -> MagicMock:
    """Wrap a dict so `.to_dict()` and attribute access both work, mirroring
    plaid-python's response objects."""
    obj = MagicMock()
    obj.to_dict.return_value = payload
    for key, value in payload.items():
        setattr(obj, key, value)
    return obj


@pytest.fixture
def make_response():
    """Return a helper that wraps a dict into a plaid-response-shaped MagicMock."""
    return _wrap
