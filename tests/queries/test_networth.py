from core.queries.networth import net_worth


def test_net_worth_sums_balances_with_correct_signs(session, queries_seed):
    """
    Seed has:
      - depository (acc_test): +1000.00
      - credit (acc_credit): -250.00 (current_balance is what's owed; subtract from net worth)
      - investment (acc_invest): +10000.00
    Expected: 1000 + 10000 - abs(-250)... wait, actually credit balance is signed:
      Plaid reports credit accounts with positive current_balance = amount owed.
      So net worth subtracts credit balances and adds depository + investment.
      Our seed puts credit current_balance at -250.00 (refund / overpayment).
      Following the rule "credit reduces net worth", net = 1000 + 10000 - (-250) = 11250?
      No — for nuance: a negative current_balance on a credit card means the bank owes YOU
      (you overpaid). So that should ADD to net worth.

    Convention used here:
      net_worth = sum(depository + investment) - sum(credit + loan)
      where balance values for credit/loan are taken as Plaid reports them
      (positive = owed). A negative credit balance flips the sign correctly.

    With seed values:
      depository: +1000.00
      investment: +10000.00
      credit:     -250.00 (we owe -250, i.e., bank owes us 250 → net worth +250)

    Expected: 1000 + 10000 - (-250) = 11250.00.
    """
    result = net_worth(session)
    assert result["total"] == 11250.00
    assert result["depository"] == 1000.00
    assert result["credit"] == -250.00       # raw sum from Plaid convention
    assert result["investment"] == 10000.00
    assert result["loan"] == 0.0


def test_net_worth_with_no_accounts(session):
    """Empty DB → all zeros."""
    result = net_worth(session)
    assert result["total"] == 0.0
    assert result["depository"] == 0.0
    assert result["credit"] == 0.0
    assert result["investment"] == 0.0
    assert result["loan"] == 0.0


def test_net_worth_includes_only_accounts_with_balance(session, queries_seed):
    """Account with NULL current_balance is treated as 0.0 — doesn't crash, doesn't skew."""
    from core.db import Account, Item

    null_balance = Account(
        account_id="acc_unknown",
        item_id="item_test",
        name="Unknown",
        type="depository",
        subtype="checking",
        current_balance=None,
    )
    session.add(null_balance)
    session.commit()

    result = net_worth(session)
    # Same as before — null treated as 0.
    assert result["total"] == 11250.00
