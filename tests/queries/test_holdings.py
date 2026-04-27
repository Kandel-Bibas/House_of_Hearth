from core.queries.holdings import list_holdings


def test_list_holdings_joins_securities(session, queries_seed):
    """Each holding row gets ticker_symbol + security name from the joined Security row."""
    rows = list_holdings(session)
    assert len(rows) == 1
    h = rows[0]
    assert h["account_id"] == "acc_invest"
    assert h["security_id"] == "sec_VTI"
    assert h["ticker_symbol"] == "VTI"
    assert h["security_name"] == "Vanguard Total Stock Market"
    assert h["quantity"] == 40.0
    assert h["institution_value"] == 10000.00
    assert h["security_type"] == "etf"


def test_list_holdings_empty_when_no_holdings(session, seeded_chain):
    """seeded_chain has no holdings; list_holdings returns []."""
    assert list_holdings(session) == []


def test_list_holdings_includes_account_name(session, queries_seed):
    """Each row includes the human-readable account name (not just the id)."""
    rows = list_holdings(session)
    assert rows[0]["account_name"] == "Brokerage"
