from sqlalchemy import select

from core.db import Account, Institution, Item
from core.plaid.link import create_link_token, exchange_public_token
from core.plaid.tokens import load_decrypted_token


def test_create_link_token_calls_plaid_and_returns_token(
    fake_plaid_client, make_response
):
    fake_plaid_client.link_token_create.return_value = make_response(
        {"link_token": "link-sandbox-12345", "expiration": "2026-04-27T00:00:00Z"}
    )

    token = create_link_token(
        client=fake_plaid_client,
        client_user_id="local-user",
    )
    assert token == "link-sandbox-12345"
    fake_plaid_client.link_token_create.assert_called_once()


def test_exchange_public_token_persists_item_institution_accounts(
    fake_plaid_client, make_response, session, fake_keychain
):
    # Plaid's /item/public_token/exchange returns access_token + item_id.
    fake_plaid_client.item_public_token_exchange.return_value = make_response(
        {"access_token": "access-sandbox-xyz", "item_id": "item_NEW"}
    )
    # Plaid's /accounts/get returns the institution_id + accounts list.
    fake_plaid_client.accounts_get.return_value = make_response(
        {
            "item": {"item_id": "item_NEW", "institution_id": "ins_wf"},
            "accounts": [
                {
                    "account_id": "acc_NEW_1",
                    "name": "Plaid Checking",
                    "official_name": "Wells Premier Checking",
                    "type": "depository",
                    "subtype": "checking",
                    "mask": "0000",
                    "balances": {
                        "current": 1234.56,
                        "available": 1234.56,
                        "limit": None,
                        "iso_currency_code": "USD",
                    },
                },
                {
                    "account_id": "acc_NEW_2",
                    "name": "Plaid Savings",
                    "official_name": None,
                    "type": "depository",
                    "subtype": "savings",
                    "mask": "1111",
                    "balances": {
                        "current": 5000.00,
                        "available": 5000.00,
                        "limit": None,
                        "iso_currency_code": "USD",
                    },
                },
            ],
        }
    )
    # Plaid's /institutions/get_by_id returns metadata for the bank.
    fake_plaid_client.institutions_get_by_id.return_value = make_response(
        {
            "institution": {
                "institution_id": "ins_wf",
                "name": "Wells Fargo",
                "primary_color": "#d71e28",
                "url": "https://wellsfargo.com",
                "logo": None,
            }
        }
    )

    item_id = exchange_public_token(
        client=fake_plaid_client,
        session=session,
        public_token="public-sandbox-pub",
    )
    assert item_id == "item_NEW"

    # Confirm rows landed.
    inst = session.scalar(select(Institution).where(Institution.institution_id == "ins_wf"))
    assert inst.name == "Wells Fargo"

    item = session.scalar(select(Item).where(Item.item_id == "item_NEW"))
    assert item.institution_id == "ins_wf"
    # Token was encrypted and stored — we can decrypt it back.
    assert load_decrypted_token(session, item_id="item_NEW") == "access-sandbox-xyz"

    accounts = session.scalars(select(Account).where(Account.item_id == "item_NEW")).all()
    assert len(accounts) == 2
    a1 = next(a for a in accounts if a.account_id == "acc_NEW_1")
    assert a1.name == "Plaid Checking"
    assert a1.official_name == "Wells Premier Checking"
    assert a1.current_balance == 1234.56
    assert a1.subtype == "checking"
    assert a1.iso_currency_code == "USD"


def test_exchange_does_not_create_duplicate_institution(
    fake_plaid_client, make_response, session, seeded_chain, fake_keychain
):
    """If the institution already exists (from a prior link), reuse it."""
    fake_plaid_client.item_public_token_exchange.return_value = make_response(
        {"access_token": "access-sandbox-xyz", "item_id": "item_NEW2"}
    )
    fake_plaid_client.accounts_get.return_value = make_response(
        {
            "item": {"item_id": "item_NEW2", "institution_id": "ins_test"},
            "accounts": [
                {
                    "account_id": "acc_NEW2_1",
                    "name": "Other Checking",
                    "official_name": None,
                    "type": "depository",
                    "subtype": "checking",
                    "mask": "2222",
                    "balances": {
                        "current": 100.0,
                        "available": 100.0,
                        "limit": None,
                        "iso_currency_code": "USD",
                    },
                },
            ],
        }
    )
    # institutions_get_by_id should NOT be called when the row already exists,
    # but the implementation may call it idempotently — either is fine. We
    # don't assert on it.

    exchange_public_token(
        client=fake_plaid_client,
        session=session,
        public_token="public-sandbox-pub",
    )

    institutions = session.scalars(select(Institution)).all()
    # ins_test from seeded_chain + (no new ins, since institution_id matches)
    assert len(institutions) == 1
    assert institutions[0].institution_id == "ins_test"
