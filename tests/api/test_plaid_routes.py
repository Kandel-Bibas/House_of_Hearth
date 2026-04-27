from sqlalchemy import select

from core.db import Item
from core.plaid.tokens import load_decrypted_token


def test_link_token_route(client_with_plaid, fake_plaid_client, make_response):
    fake_plaid_client.link_token_create.return_value = make_response(
        {"link_token": "link-sandbox-XYZ", "expiration": "2026-04-27T00:00:00Z"}
    )
    resp = client_with_plaid.post("/plaid/link-token")
    assert resp.status_code == 200
    assert resp.json() == {"link_token": "link-sandbox-XYZ"}


def test_exchange_route(
    client_with_plaid, fake_plaid_client, make_response, fake_keychain
):
    fake_plaid_client.item_public_token_exchange.return_value = make_response(
        {"access_token": "access-sandbox-XYZ", "item_id": "item_NEW"}
    )
    fake_plaid_client.accounts_get.return_value = make_response(
        {
            "item": {"item_id": "item_NEW", "institution_id": "ins_test"},
            "accounts": [
                {
                    "account_id": "acc_NEW",
                    "name": "Plaid Checking",
                    "official_name": None,
                    "type": "depository",
                    "subtype": "checking",
                    "mask": "0000",
                    "balances": {
                        "current": 1234.56,
                        "available": 1234.56,
                        "limit": None,
                        "iso_currency_code": "USD",
                    },
                }
            ],
        }
    )
    fake_plaid_client.institutions_get_by_id.return_value = make_response(
        {
            "institution": {
                "institution_id": "ins_test",
                "name": "Test Bank",
                "primary_color": "#000",
                "url": "https://test.example",
                "logo": None,
            }
        }
    )

    resp = client_with_plaid.post(
        "/plaid/exchange", json={"public_token": "public-sandbox-PUB"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"item_id": "item_NEW"}


def test_exchange_with_missing_public_token_returns_422(client_with_plaid):
    resp = client_with_plaid.post("/plaid/exchange", json={})
    assert resp.status_code == 422
