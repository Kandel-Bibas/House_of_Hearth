import pytest

from core.plaid.client import PlaidEnv, make_plaid_client


def test_make_plaid_client_returns_plaid_api_object():
    """The factory should return a usable PlaidApi instance, not a raw config."""
    client = make_plaid_client(env=PlaidEnv.SANDBOX, client_id="cid", secret="sec")
    # Must have the methods we'll actually call.
    assert hasattr(client, "link_token_create")
    assert hasattr(client, "item_public_token_exchange")
    assert hasattr(client, "transactions_sync")
    assert hasattr(client, "accounts_get")
    assert hasattr(client, "investments_holdings_get")


def test_make_plaid_client_routes_each_env_to_correct_host():
    """Each env should produce a client pointing at the matching Plaid host."""
    for env, expected_host in [
        (PlaidEnv.SANDBOX, "sandbox.plaid.com"),
        (PlaidEnv.DEVELOPMENT, "development.plaid.com"),
        (PlaidEnv.PRODUCTION, "production.plaid.com"),
    ]:
        client = make_plaid_client(env=env, client_id="cid", secret="sec")
        # The host is on the underlying api_client.configuration.host.
        host = client.api_client.configuration.host
        assert expected_host in host, f"env={env} produced host {host}"


def test_invalid_env_string_raises():
    with pytest.raises(ValueError):
        PlaidEnv("not_a_real_env")
