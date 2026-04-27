"""Read-side query functions used by both api/ and mcp/.

Public API:
- search_transactions
- net_worth
- category_spend
- list_holdings
- list_accounts

All functions take a SQLAlchemy `Session` as the first positional arg, return
JSON-safe dicts (or lists thereof), and never write to the database.
"""
from core.queries.accounts import list_accounts
from core.queries.categories import category_spend
from core.queries.holdings import list_holdings
from core.queries.networth import net_worth
from core.queries.transactions import search_transactions

__all__ = [
    "category_spend",
    "list_accounts",
    "list_holdings",
    "net_worth",
    "search_transactions",
]
