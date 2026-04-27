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
    """Each live env produces a client pointing at the matching Plaid host."""
    for env, expected_host in [
        (PlaidEnv.SANDBOX, "sandbox.plaid.com"),
        (PlaidEnv.PRODUCTION, "production.plaid.com"),
    ]:
        client = make_plaid_client(env=env, client_id="cid", secret="sec")
        host = client.api_client.configuration.host
        assert expected_host in host, f"env={env} produced host {host}"


def test_development_env_raises_with_clear_message():
    """Plaid retired Development in early 2025; constructing a client should
    fail loudly rather than fail later with a DNS error."""
    with pytest.raises(ValueError, match="DEVELOPMENT"):
        make_plaid_client(env=PlaidEnv.DEVELOPMENT, client_id="cid", secret="sec")


def test_invalid_env_string_raises():
    with pytest.raises(ValueError):
        PlaidEnv("not_a_real_env")
