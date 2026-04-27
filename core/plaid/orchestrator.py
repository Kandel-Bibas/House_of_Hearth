"""Sync orchestrator: per-Item locks + thread-pool fan-out across Items.

Public API:
- PerItemLockRegistry — `threading.Lock` per item_id (singleton-per-id).
- sync_item(client_factory, session_factory, item_id, lock_registry=None) — full flow
  for one Item: decrypt → sync_transactions → refresh_balances → (if investment)
  refresh_holdings. Status flags maintained on the Item row.
- sync_all_items(client_factory, session_factory, item_ids, max_workers=5) — fan out.

`client_factory` and `session_factory` are zero-arg callables; each thread builds its
own client and session, so nothing is shared across threads except the lock registry
and the underlying SQLite file.
"""
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from plaid.api.plaid_api import PlaidApi
from sqlalchemy.orm import sessionmaker, Session

from core.db import Item
from core.plaid.refresh import has_investment_accounts, refresh_balances, refresh_holdings
from core.plaid.sync import sync_transactions
from core.plaid.tokens import load_decrypted_token


class PerItemLockRegistry:
    """One `threading.Lock` per item_id, lazily created."""

    def __init__(self) -> None:
        self._locks: dict[str, threading.Lock] = {}
        self._meta_lock = threading.Lock()

    def lock_for(self, item_id: str) -> threading.Lock:
        with self._meta_lock:
            if item_id not in self._locks:
                self._locks[item_id] = threading.Lock()
            return self._locks[item_id]


# Module-level default registry (callers can pass their own for tests).
_DEFAULT_REGISTRY = PerItemLockRegistry()


def sync_item(
    *,
    client_factory: Callable[[], PlaidApi],
    session_factory: Callable[[], Session] | sessionmaker,
    item_id: str,
    lock_registry: PerItemLockRegistry | None = None,
) -> None:
    """Run the full sync flow for one Item.

    Order of operations:
      1. Acquire the per-Item lock (so manual sync can't race auto-sync).
      2. Decrypt the access token (uses Keychain — first call may prompt).
      3. sync_transactions (multi-page loop).
      4. refresh_balances.
      5. If has_investment_accounts: refresh_holdings.
      6. On any exception, write status='error' to the Item, swallow the exception
         (so concurrent siblings aren't blocked when called via sync_all_items).
    """
    registry = lock_registry or _DEFAULT_REGISTRY
    lock = registry.lock_for(item_id)
    with lock:
        try:
            client = client_factory()
            with session_factory() as session:
                access_token = load_decrypted_token(session, item_id=item_id)

                sync_transactions(
                    client=client, session=session, item_id=item_id, access_token=access_token
                )
                refresh_balances(
                    client=client, session=session, item_id=item_id, access_token=access_token
                )
                if has_investment_accounts(session, item_id=item_id):
                    refresh_holdings(
                        client=client, session=session, item_id=item_id, access_token=access_token
                    )
        except Exception as exc:
            # Record the error on the Item row; don't re-raise (caller is sync_all_items).
            with session_factory() as session:
                item = session.get(Item, item_id)
                if item is not None:
                    item.last_sync_status = "error"
                    item.last_sync_error = f"{type(exc).__name__}: {exc}"
                    session.commit()


def sync_all_items(
    *,
    client_factory: Callable[[], PlaidApi],
    session_factory: Callable[[], Session] | sessionmaker,
    item_ids: list[str],
    max_workers: int = 5,
    lock_registry: PerItemLockRegistry | None = None,
) -> None:
    """Run sync_item across `item_ids` in parallel via a ThreadPoolExecutor."""
    registry = lock_registry or _DEFAULT_REGISTRY
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        list(
            pool.map(
                lambda iid: sync_item(
                    client_factory=client_factory,
                    session_factory=session_factory,
                    item_id=iid,
                    lock_registry=registry,
                ),
                item_ids,
            )
        )
