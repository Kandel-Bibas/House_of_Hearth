"""Per-test seeder helper for queries tests.

Builds on the shared `seeded_chain` fixture from `tests/conftest.py`
(institution → item → account) by adding investment account, securities, holdings,
and a small fixed set of transactions covering different categories and dates.
"""
from datetime import date, datetime

import pytest

from core.db import Account, Holding, Item, Security, Transaction


@pytest.fixture
def queries_seed(session, seeded_chain):
    """Extend the base seed with two more accounts (one credit, one investment),
    one security, two holdings, and 6 transactions across categories.

    Returns a dict with each created object so tests can reference them.
    """
    inst = seeded_chain["institution"]  # ins_test
    item = seeded_chain["item"]          # item_test
    base_acct = seeded_chain["account"]  # acc_test, depository checking, balance 1000.00

    credit_acct = Account(
        account_id="acc_credit",
        item_id=item.item_id,
        name="Credit Card",
        type="credit",
        subtype="credit card",
        current_balance=-250.00,        # owed
        limit_balance=5000.00,
        iso_currency_code="USD",
    )
    invest_acct = Account(
        account_id="acc_invest",
        item_id=item.item_id,
        name="Brokerage",
        type="investment",
        subtype="brokerage",
        current_balance=10000.00,
        iso_currency_code="USD",
    )
    sec = Security(
        security_id="sec_VTI",
        ticker_symbol="VTI",
        name="Vanguard Total Stock Market",
        type="etf",
        close_price=250.00,
    )
    holding = Holding(
        account_id="acc_invest",
        security_id="sec_VTI",
        quantity=40.0,
        institution_price=250.00,
        institution_value=10000.00,
    )

    txns = [
        Transaction(
            transaction_id="txn_grocery_1",
            account_id=base_acct.account_id,
            date=date(2026, 4, 1),
            amount=42.50,
            name="WHOLE FOODS",
            merchant_name="Whole Foods",
            payment_channel="in store",
            pending=False,
            category_primary="FOOD_AND_DRINK",
            category_detailed="FOOD_AND_DRINK_GROCERIES",
        ),
        Transaction(
            transaction_id="txn_grocery_2",
            account_id=base_acct.account_id,
            date=date(2026, 4, 10),
            amount=37.25,
            name="TRADER JOES",
            merchant_name="Trader Joe's",
            payment_channel="in store",
            pending=False,
            category_primary="FOOD_AND_DRINK",
            category_detailed="FOOD_AND_DRINK_GROCERIES",
        ),
        Transaction(
            transaction_id="txn_restaurant_1",
            account_id=base_acct.account_id,
            date=date(2026, 4, 5),
            amount=85.00,
            name="CHEZ PANISSE",
            merchant_name="Chez Panisse",
            payment_channel="in store",
            pending=False,
            category_primary="FOOD_AND_DRINK",
            category_detailed="FOOD_AND_DRINK_RESTAURANTS",
        ),
        Transaction(
            transaction_id="txn_gas_1",
            account_id=credit_acct.account_id,
            date=date(2026, 4, 12),
            amount=55.00,
            name="SHELL #1234",
            merchant_name="Shell",
            payment_channel="in store",
            pending=False,
            category_primary="TRANSPORTATION",
            category_detailed="TRANSPORTATION_GAS",
        ),
        Transaction(
            transaction_id="txn_paycheck",
            account_id=base_acct.account_id,
            date=date(2026, 4, 15),
            amount=-3000.00,                # negative = inflow per Plaid convention
            name="ACME CORP PAYROLL",
            merchant_name="Acme Corp",
            payment_channel="other",
            pending=False,
            category_primary="INCOME",
            category_detailed="INCOME_WAGES",
        ),
        Transaction(
            transaction_id="txn_removed",   # soft-deleted — should be excluded by default
            account_id=base_acct.account_id,
            date=date(2026, 4, 8),
            amount=20.00,
            name="OLD TXN",
            merchant_name="Old Vendor",
            payment_channel="online",
            pending=False,
            category_primary="GENERAL_MERCHANDISE",
            category_detailed="GENERAL_MERCHANDISE_OTHER",
            removed_at=datetime(2026, 4, 9),
        ),
    ]

    session.add_all([credit_acct, invest_acct, sec, holding, *txns])
    session.commit()

    return {
        "institution": inst,
        "item": item,
        "depository": base_acct,
        "credit": credit_acct,
        "investment": invest_acct,
        "security": sec,
        "holding": holding,
        "txns": txns,
    }
