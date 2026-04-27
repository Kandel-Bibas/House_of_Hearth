"""MCP tool implementations — read-only wrappers over core.queries.

Each tool returns a list[dict] or dict; the FastMCP framework JSON-encodes them.
If the schema check failed, every tool returns an error dict.
"""
from datetime import date as date_t
from typing import Any, Optional

from sqlalchemy.orm import sessionmaker

from core.queries import (
    category_spend as q_category_spend,
    list_accounts as q_list_accounts,
    list_holdings as q_list_holdings,
    net_worth as q_net_worth,
    search_transactions as q_search_transactions,
)


def register(
    server: Any,
    *,
    session_factory: sessionmaker,
    schema_ok: bool,
    schema_msg: str,
) -> None:
    """Attach all 5 tools to the FastMCP server."""

    def _guard() -> Optional[dict[str, str]]:
        if not schema_ok:
            return {"error": schema_msg}
        return None

    @server.tool()
    def search_transactions(
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        account_id: Optional[str] = None,
        category_primary: Optional[str] = None,
        category_detailed: Optional[str] = None,
        merchant_name: Optional[str] = None,
        min_amount: Optional[float] = None,
        max_amount: Optional[float] = None,
        include_removed: bool = False,
        limit: Optional[int] = None,
    ) -> list[dict[str, Any]] | dict[str, str]:
        """Search transactions with filters. Dates are ISO strings (YYYY-MM-DD).

        Defaults exclude soft-deleted rows. Returns transactions newest first.
        """
        if (g := _guard()):
            return g
        with session_factory() as s:
            return q_search_transactions(
                s,
                start_date=date_t.fromisoformat(start_date) if start_date else None,
                end_date=date_t.fromisoformat(end_date) if end_date else None,
                account_id=account_id,
                category_primary=category_primary,
                category_detailed=category_detailed,
                merchant_name=merchant_name,
                min_amount=min_amount,
                max_amount=max_amount,
                include_removed=include_removed,
                limit=limit,
            )

    @server.tool()
    def net_worth() -> dict[str, Any]:
        """Compute net worth across all linked accounts.

        Returns: {total, depository, credit, investment, loan}.
        """
        if (g := _guard()):
            return g
        with session_factory() as s:
            return q_net_worth(s)

    @server.tool()
    def category_spend(
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]] | dict[str, str]:
        """Sum outflows by category over [start_date, end_date]. Inflows excluded.

        Returns: list of {category_primary, total, count}, sorted by total desc.
        """
        if (g := _guard()):
            return g
        with session_factory() as s:
            return q_category_spend(
                s,
                start_date=date_t.fromisoformat(start_date),
                end_date=date_t.fromisoformat(end_date),
            )

    @server.tool()
    def list_holdings() -> list[dict[str, Any]] | dict[str, str]:
        """Current investment holdings, joined with security and account metadata."""
        if (g := _guard()):
            return g
        with session_factory() as s:
            return q_list_holdings(s)

    @server.tool()
    def list_accounts() -> list[dict[str, Any]] | dict[str, str]:
        """All linked accounts with institution name, balance, and last-sync status."""
        if (g := _guard()):
            return g
        with session_factory() as s:
            return q_list_accounts(s)
