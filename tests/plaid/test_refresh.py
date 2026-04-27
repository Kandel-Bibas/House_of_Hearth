from sqlalchemy import select

from core.db import Account, Holding, Item, Security
from core.plaid.refresh import has_investment_accounts, refresh_balances, refresh_holdings


def _accounts_get_response(make_response, accounts: list[dict]):
    return make_response(
        {
            "item": {"item_id": "item_test", "institution_id": "ins_test"},
            "accounts": accounts,
        }
    )


def _holdings_get_response(make_response, holdings: list[dict], securities: list[dict], accounts: list[dict]):
    return make_response(
        {
            "accounts": accounts,
            "holdings": holdings,
            "securities": securities,
            "item": {"item_id": "item_test", "institution_id": "ins_test"},
        }
    )


# ----------- refresh_balances -----------------------------------------------


def test_refresh_balances_overwrites_account_balance_columns(
    session, seeded_chain, fake_plaid_client, make_response
):
    fake_plaid_client.accounts_get.return_value = _accounts_get_response(
        make_response,
        [
            {
                "account_id": "acc_test",
                "name": "Checking",
                "official_name": None,
                "type": "depository",
                "subtype": "checking",
                "mask": "0000",
                "balances": {
                    "current": 9999.99,
                    "available": 9000.00,
                    "limit": None,
                    "iso_currency_code": "USD",
                },
            },
        ],
    )

    refresh_balances(
        client=fake_plaid_client,
        session=session,
        item_id="item_test",
        access_token="access-sandbox-xyz",
    )

    acct = session.scalar(select(Account).where(Account.account_id == "acc_test"))
    assert acct.current_balance == 9999.99
    assert acct.available_balance == 9000.00
    assert acct.last_balance_at is not None


def test_refresh_balances_inserts_account_seen_for_first_time(
    session, seeded_chain, fake_plaid_client, make_response
):
    """If Plaid reports an account we don't have a row for, insert it. (User added a new
    sub-account at their bank since the original link.)"""
    fake_plaid_client.accounts_get.return_value = _accounts_get_response(
        make_response,
        [
            # Existing
            {
                "account_id": "acc_test",
                "name": "Checking",
                "official_name": None,
                "type": "depository",
                "subtype": "checking",
                "mask": "0000",
                "balances": {
                    "current": 1000.00,
                    "available": 1000.00,
                    "limit": None,
                    "iso_currency_code": "USD",
                },
            },
            # New
            {
                "account_id": "acc_brand_new",
                "name": "New Savings",
                "official_name": None,
                "type": "depository",
                "subtype": "savings",
                "mask": "9999",
                "balances": {
                    "current": 500.00,
                    "available": 500.00,
                    "limit": None,
                    "iso_currency_code": "USD",
                },
            },
        ],
    )

    refresh_balances(
        client=fake_plaid_client,
        session=session,
        item_id="item_test",
        access_token="access-sandbox-xyz",
    )

    accts = session.scalars(select(Account).where(Account.item_id == "item_test")).all()
    assert {a.account_id for a in accts} == {"acc_test", "acc_brand_new"}


# ----------- has_investment_accounts ----------------------------------------


def test_has_investment_accounts_true_when_any(session, seeded_chain):
    inv = Account(
        account_id="acc_brokerage",
        item_id="item_test",
        name="Brokerage",
        type="investment",
        subtype="brokerage",
    )
    session.add(inv)
    session.commit()

    assert has_investment_accounts(session, item_id="item_test") is True


def test_has_investment_accounts_false_when_none(session, seeded_chain):
    # seeded_chain only has a depository account.
    assert has_investment_accounts(session, item_id="item_test") is False


# ----------- refresh_holdings -----------------------------------------------


def test_refresh_holdings_upserts_securities_and_overwrites_holdings(
    session, seeded_chain, fake_plaid_client, make_response
):
    # First, seed an investment account (refresh_holdings expects the account row to exist).
    inv = Account(
        account_id="acc_brokerage",
        item_id="item_test",
        name="Brokerage",
        type="investment",
        subtype="brokerage",
    )
    session.add(inv)
    session.commit()

    fake_plaid_client.investments_holdings_get.return_value = _holdings_get_response(
        make_response,
        holdings=[
            {
                "account_id": "acc_brokerage",
                "security_id": "sec_VTI",
                "quantity": 10.5,
                "institution_price": 250.00,
                "institution_value": 2625.00,
                "cost_basis": 2000.00,
                "iso_currency_code": "USD",
            },
        ],
        securities=[
            {
                "security_id": "sec_VTI",
                "ticker_symbol": "VTI",
                "name": "Vanguard Total Stock Market",
                "type": "etf",
                "iso_currency_code": "USD",
                "close_price": 250.00,
                "close_price_as_of": "2026-04-25",
            },
        ],
        accounts=[
            {
                "account_id": "acc_brokerage",
                "name": "Brokerage",
                "official_name": None,
                "type": "investment",
                "subtype": "brokerage",
                "mask": "5555",
                "balances": {
                    "current": 2625.00,
                    "available": None,
                    "limit": None,
                    "iso_currency_code": "USD",
                },
            },
        ],
    )

    refresh_holdings(
        client=fake_plaid_client,
        session=session,
        item_id="item_test",
        access_token="access-sandbox-xyz",
    )

    sec = session.scalar(select(Security).where(Security.security_id == "sec_VTI"))
    assert sec.ticker_symbol == "VTI"
    assert sec.close_price == 250.00

    hold = session.scalar(
        select(Holding).where(
            Holding.account_id == "acc_brokerage", Holding.security_id == "sec_VTI"
        )
    )
    assert hold.quantity == 10.5
    assert hold.institution_value == 2625.00

    # Investment account balance was refreshed too.
    inv_acct = session.scalar(select(Account).where(Account.account_id == "acc_brokerage"))
    assert inv_acct.current_balance == 2625.00


def test_refresh_holdings_overwrites_existing_holdings(
    session, seeded_chain, fake_plaid_client, make_response
):
    """A second call replaces stale holdings (no append, no double-counting)."""
    inv = Account(
        account_id="acc_brokerage",
        item_id="item_test",
        name="Brokerage",
        type="investment",
        subtype="brokerage",
    )
    sec = Security(security_id="sec_VTI", ticker_symbol="VTI", name="Vanguard")
    stale_hold = Holding(
        account_id="acc_brokerage",
        security_id="sec_VTI",
        quantity=999.0,  # wrong; will be overwritten
        institution_price=999.0,
        institution_value=999.0,
    )
    session.add_all([inv, sec, stale_hold])
    session.commit()

    fake_plaid_client.investments_holdings_get.return_value = _holdings_get_response(
        make_response,
        holdings=[
            {
                "account_id": "acc_brokerage",
                "security_id": "sec_VTI",
                "quantity": 10.0,
                "institution_price": 250.00,
                "institution_value": 2500.00,
                "cost_basis": None,
                "iso_currency_code": "USD",
            },
        ],
        securities=[
            {
                "security_id": "sec_VTI",
                "ticker_symbol": "VTI",
                "name": "Vanguard Total Stock Market",
                "type": "etf",
                "iso_currency_code": "USD",
                "close_price": 250.00,
                "close_price_as_of": "2026-04-25",
            },
        ],
        accounts=[
            {
                "account_id": "acc_brokerage",
                "name": "Brokerage",
                "official_name": None,
                "type": "investment",
                "subtype": "brokerage",
                "mask": "5555",
                "balances": {
                    "current": 2500.00,
                    "available": None,
                    "limit": None,
                    "iso_currency_code": "USD",
                },
            },
        ],
    )

    refresh_holdings(
        client=fake_plaid_client,
        session=session,
        item_id="item_test",
        access_token="access-sandbox-xyz",
    )

    holdings = session.scalars(select(Holding)).all()
    assert len(holdings) == 1
    assert holdings[0].quantity == 10.0
    assert holdings[0].institution_value == 2500.00
