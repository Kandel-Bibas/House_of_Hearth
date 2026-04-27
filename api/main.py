"""FastAPI app entry point.

Run with: `uvicorn api.main:app --reload --port 8000`

Startup:
  1. Run Alembic migrations.
  2. Pre-warm the Keychain master key (so the user gets a single prompt at boot).
  3. Schedule a background auto-sync of all linked Items.
"""
import os
import subprocess
import sys
import threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.deps import get_engine, get_plaid_client, get_session_factory


def _run_alembic_upgrade() -> None:
    """Run `alembic upgrade head` against the configured DATABASE_URL.

    Tests skip this by setting FINANCE_TRACKER_SKIP_STARTUP=1.
    """
    repo_root = Path(__file__).resolve().parent.parent
    db_url = os.environ.get("DATABASE_URL")
    env = {**os.environ, **({"DATABASE_URL": db_url} if db_url else {})}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=repo_root,
        env=env,
        check=False,  # don't crash startup; if migrations fail the user sees logs
    )


def _auto_sync_in_background() -> None:
    """Kick off sync_all_items in a daemon thread so the API serves immediately."""
    from sqlalchemy import select

    from core.db import Item
    from core.plaid.orchestrator import sync_all_items

    SessionLocal = get_session_factory()
    with SessionLocal() as s:
        item_ids = [r[0] for r in s.execute(select(Item.item_id)).all()]

    if not item_ids:
        return

    def runner():
        sync_all_items(
            client_factory=get_plaid_client,
            session_factory=SessionLocal,
            item_ids=item_ids,
        )

    threading.Thread(target=runner, daemon=True).start()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Finance Tracker",
        version="0.1.0",
        description="Local-first personal finance tracker.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from api.routes import (
        accounts as accounts_routes,
        categories as categories_routes,
        holdings as holdings_routes,
        networth as networth_routes,
        plaid as plaid_routes,
        sync as sync_routes,
        transactions as transactions_routes,
    )
    app.include_router(plaid_routes.router)
    app.include_router(accounts_routes.router)
    app.include_router(transactions_routes.router)
    app.include_router(holdings_routes.router)
    app.include_router(networth_routes.router)
    app.include_router(categories_routes.router)
    app.include_router(sync_routes.router)

    @app.on_event("startup")
    def _startup():
        if os.environ.get("FINANCE_TRACKER_SKIP_STARTUP") == "1":
            return
        _run_alembic_upgrade()
        # Pre-warm Keychain (single prompt for the user).
        try:
            from core.crypto import get_or_create_master_key
            get_or_create_master_key()
        except Exception:
            pass  # log but don't crash
        _auto_sync_in_background()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
