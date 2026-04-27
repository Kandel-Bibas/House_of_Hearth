"""Local MCP server for the Finance Tracker.

Exposes 5 read-only tools that wrap core.queries.*. Opens SQLite in
read-only mode; never imports core.crypto; cannot reach Plaid.

Run via: `python -m mcp_server` (from the project root).

At startup, verifies the DB schema is at Alembic head. If not, returns
errors from every tool with a clear message instead of risking stale data.
"""
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

REPO_ROOT = Path(__file__).resolve().parent.parent

logger = logging.getLogger("finance_tracker_mcp")
# stderr only — stdin/stdout are reserved for MCP JSON-RPC framing.
logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                    format="%(asctime)s %(levelname)s %(message)s")


def _schema_is_current() -> tuple[bool, str]:
    """Return (ok, message). Compares `alembic current` with `alembic heads`.

    Returns (False, why) if the DB is missing or behind HEAD; (True, "ok") otherwise.
    """
    db_url = os.environ.get("DATABASE_URL", "sqlite:///finance.db")
    if not db_url.startswith("sqlite"):
        return True, "skip-check (non-sqlite)"

    db_path = db_url.replace("sqlite:///", "")
    if not Path(db_path).is_absolute():
        db_path = str(REPO_ROOT / db_path)
    if not Path(db_path).exists():
        return False, f"DB file does not exist at {db_path}. Open the app once to initialize."

    env = {**os.environ, "DATABASE_URL": db_url}

    def _alembic(cmd: str) -> str:
        return subprocess.run(
            [sys.executable, "-m", "alembic", cmd],
            cwd=REPO_ROOT,
            capture_output=True, text=True, env=env,
        ).stdout.strip()

    current = _alembic("current")
    heads = _alembic("heads")

    # Both come back like "<rev> (head)" / "<rev>"; compare on the rev token.
    cur_rev = current.split()[0] if current else ""
    head_rev = heads.split()[0] if heads else ""
    if cur_rev and head_rev and cur_rev == head_rev:
        return True, "ok"
    return False, f"Schema out of date. current={cur_rev or '(none)'} head={head_rev or '(none)'} — open the app once to migrate."


def _make_readonly_session_factory():
    """Open SQLite in read-only mode using a URI-style connect string.

    SQLAlchemy passes through `?mode=ro` when we use a URI URL (file:... ).
    """
    db_url = os.environ.get("DATABASE_URL", "sqlite:///finance.db")
    if db_url.startswith("sqlite:///"):
        db_path = db_url.replace("sqlite:///", "")
        if not Path(db_path).is_absolute():
            db_path = str(REPO_ROOT / db_path)
        ro_url = f"sqlite:///file:{db_path}?mode=ro&uri=true"
        engine = create_engine(ro_url, future=True)
    else:
        # Non-sqlite: best-effort, no read-only enforcement.
        engine = create_engine(db_url, future=True)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def build_server(*, skip_schema_check: bool = False) -> FastMCP:
    """Build and return a FastMCP server with all tools registered.

    If the schema check fails (and we're not skipping), every tool will refuse
    to run and return a clear error string instead.
    """
    server = FastMCP("finance-tracker")

    if not skip_schema_check:
        ok, msg = _schema_is_current()
    else:
        ok, msg = True, "skipped"

    SessionLocal = _make_readonly_session_factory()

    # Import and register tools.
    from mcp_server import tools as tool_impls

    tool_impls.register(server, session_factory=SessionLocal, schema_ok=ok, schema_msg=msg)

    return server
