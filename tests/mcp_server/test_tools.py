"""Per-tool smoke tests — verify each tool returns expected shape end-to-end."""
from unittest.mock import MagicMock

import pytest

from core.db import make_session_factory
from mcp_server import tools as tool_impls


@pytest.fixture
def server_with_seed(engine, queries_seed, seeded_chain):
    """A MagicMock 'server' that records registered tools, hooked to the test DB."""
    SessionLocal = make_session_factory(engine)

    registered: dict[str, callable] = {}

    class FakeServer:
        def tool(self):
            def decorator(fn):
                registered[fn.__name__] = fn
                return fn
            return decorator

    server = FakeServer()
    tool_impls.register(server, session_factory=SessionLocal, schema_ok=True, schema_msg="ok")
    return registered


def test_search_transactions_tool(server_with_seed):
    fn = server_with_seed["search_transactions"]
    rows = fn()
    assert isinstance(rows, list)
    assert len(rows) == 5  # 5 non-removed in queries_seed


def test_search_transactions_with_filters(server_with_seed):
    fn = server_with_seed["search_transactions"]
    rows = fn(category_primary="FOOD_AND_DRINK")
    assert isinstance(rows, list)
    assert all(r["category_primary"] == "FOOD_AND_DRINK" for r in rows)
    assert len(rows) == 3


def test_net_worth_tool(server_with_seed):
    fn = server_with_seed["net_worth"]
    result = fn()
    assert result["total"] == 11250.0
    assert result["depository"] == 1000.0


def test_category_spend_tool(server_with_seed):
    fn = server_with_seed["category_spend"]
    rows = fn(start_date="2026-04-01", end_date="2026-04-30")
    assert isinstance(rows, list)
    by_cat = {r["category_primary"]: r["total"] for r in rows}
    assert by_cat["FOOD_AND_DRINK"] == 164.75


def test_list_holdings_tool(server_with_seed):
    fn = server_with_seed["list_holdings"]
    rows = fn()
    assert len(rows) == 1
    assert rows[0]["ticker_symbol"] == "VTI"


def test_list_accounts_tool(server_with_seed):
    fn = server_with_seed["list_accounts"]
    rows = fn()
    assert len(rows) == 3
    by_id = {r["account_id"]: r for r in rows}
    assert by_id["acc_test"]["institution_name"] == "Test Bank"


def test_tools_return_error_when_schema_check_failed():
    """When schema_ok=False, every tool returns {"error": <msg>} instead of running."""
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import create_engine

    fake_session_factory = sessionmaker(bind=create_engine("sqlite:///:memory:", future=True))

    registered = {}

    class FakeServer:
        def tool(self):
            def decorator(fn):
                registered[fn.__name__] = fn
                return fn
            return decorator

    tool_impls.register(
        FakeServer(),
        session_factory=fake_session_factory,
        schema_ok=False,
        schema_msg="schema out of date",
    )

    for name in ("search_transactions", "net_worth", "list_accounts", "list_holdings"):
        result = registered[name]()
        assert result == {"error": "schema out of date"}, f"tool {name} did not guard"

    # category_spend has required args; check it too.
    cs = registered["category_spend"](start_date="2026-04-01", end_date="2026-04-30")
    assert cs == {"error": "schema out of date"}
