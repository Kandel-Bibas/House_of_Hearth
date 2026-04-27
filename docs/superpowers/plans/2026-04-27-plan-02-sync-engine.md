# Plan 2 — Sync Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the `core/plaid/` package: env-aware Plaid client, Link flow (create + exchange + persist), transactions sync with cursor atomicity, balance refresh, holdings refresh, and a sync orchestrator that runs Items in parallel with per-Item locking. Tested against a fake Plaid client; one optional ring against Plaid Sandbox.

**Architecture decision (locked):** Pure sync DB (SQLAlchemy `Session`, not `AsyncSession`). Parallelism comes from `concurrent.futures.ThreadPoolExecutor` for HTTP fan-out across Items. SQLite is single-writer in any case, and async over ~5 Items adds complexity for no measurable benefit. The spec's `async with db.transaction()` is reinterpreted as `with session.begin()`.

**Tech Stack:** `plaid-python>=24.0,<32`, `concurrent.futures` (stdlib), existing Plan 1 stack (SQLAlchemy 2.x, cryptography, keyring, pytest).

**Spec reference:** `docs/superpowers/specs/2026-04-26-finance-tracker-design.md` — sections 5.1 (link flow), 5.2 (sync flow), 7.2 (error mapping), 7.3 (cursor atomicity), 7.4 (concurrency).

---

## File Structure (created by this plan)

```
finance-tracker/
├── core/
│   ├── db/
│   │   └── __init__.py                # MODIFIED: add re-exports
│   ├── plaid/                         # NEW package
│   │   ├── __init__.py                # public API
│   │   ├── client.py                  # plaid-python wrapper, env routing
│   │   ├── tokens.py                  # encrypt+persist / load+decrypt helpers
│   │   ├── link.py                    # create_link_token, exchange_public_token
│   │   ├── errors.py                  # Plaid error → SyncStatus mapping
│   │   ├── sync.py                    # apply_sync_page, sync_transactions
│   │   ├── refresh.py                 # refresh_balances, refresh_holdings
│   │   └── orchestrator.py            # sync_item, sync_all_items, per-Item locks
│   └── ...
├── migrations/
│   └── env.py                         # MODIFIED: read DATABASE_URL env var
├── tests/
│   ├── conftest.py                    # NEW: shared fixtures (engine, session, seeded_chain, fake_keychain)
│   ├── db/
│   │   ├── test_migration.py          # MODIFIED: use sys.executable -m alembic + env var
│   │   └── test_models.py             # MODIFIED: drop unused timezone import
│   └── plaid/                         # NEW
│       ├── __init__.py
│       ├── conftest.py                # plaid-specific fixtures (fake_client, canned responses)
│       ├── test_client.py
│       ├── test_tokens.py
│       ├── test_link.py
│       ├── test_errors.py
│       ├── test_sync.py               # the load-bearing test file (atomicity, idempotency, paging)
│       ├── test_refresh.py
│       ├── test_orchestrator.py
│       └── test_sandbox_integration.py  # marked @pytest.mark.sandbox, skipped by default
└── pyproject.toml                     # MODIFIED: add plaid-python, mark sandbox marker
```

---

## Task 1: Polish prep (foundation cleanup before Plaid work)

This bundles the items the Plan 1 final reviewer flagged as worth doing before Plan 2 starts. Single commit, single concern: clean prerequisites.

**Files:**
- Modify: `core/db/__init__.py` (currently empty)
- Modify: `migrations/env.py`
- Create: `tests/conftest.py`
- Modify: `tests/db/test_migration.py`
- Modify: `tests/db/test_models.py`
- Modify: `pyproject.toml` (register `sandbox` pytest marker)

- [ ] **Step 1: Add re-exports to `core/db/__init__.py`**

Replace the empty `core/db/__init__.py` with:

```python
"""Database package — SQLAlchemy models, session factories, migrations.

Public API:
- Base, Institution, Item, Account, Transaction, Security, Holding
- make_engine, make_session_factory, DEFAULT_DATABASE_URL
"""
from core.db.models import (
    Account,
    Base,
    Holding,
    Institution,
    Item,
    Security,
    Transaction,
)
from core.db.session import (
    DEFAULT_DATABASE_URL,
    make_engine,
    make_session_factory,
)

__all__ = [
    "Account",
    "Base",
    "DEFAULT_DATABASE_URL",
    "Holding",
    "Institution",
    "Item",
    "Security",
    "Transaction",
    "make_engine",
    "make_session_factory",
]
```

- [ ] **Step 2: Make `migrations/env.py` honor `DATABASE_URL`**

Replace `migrations/env.py` with:

```python
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from core.db.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Honor DATABASE_URL if set (overrides alembic.ini default).
# Tests set this via env={"DATABASE_URL": ...}; CLI users can `DATABASE_URL=... alembic upgrade head`.
_env_url = os.environ.get("DATABASE_URL")
if _env_url:
    config.set_main_option("sqlalchemy.url", _env_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 3: Simplify `tests/db/test_migration.py`**

Replace the entire content of `tests/db/test_migration.py` with:

```python
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import inspect

from core.db import Base, make_engine

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_alembic(db_path: Path, *args: str) -> subprocess.CompletedProcess:
    """Run alembic via the running interpreter, with DATABASE_URL pointing at the temp DB."""
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}"}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )


def test_alembic_upgrade_creates_all_tables(tmp_path):
    db_path = tmp_path / "migrated.db"
    result = _run_alembic(db_path, "upgrade", "head")
    assert result.returncode == 0, (
        f"alembic upgrade failed:\nstdout:{result.stdout}\nstderr:{result.stderr}"
    )

    engine = make_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    tables_after_alembic = set(inspector.get_table_names()) - {"alembic_version"}
    assert tables_after_alembic == set(Base.metadata.tables.keys())


def test_alembic_downgrade_to_base(tmp_path):
    db_path = tmp_path / "migrated.db"

    up = _run_alembic(db_path, "upgrade", "head")
    assert up.returncode == 0, up.stderr
    down = _run_alembic(db_path, "downgrade", "base")
    assert down.returncode == 0, down.stderr

    engine = make_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    tables = set(inspector.get_table_names()) - {"alembic_version"}
    assert tables == set()
```

- [ ] **Step 4: Drop unused import in `tests/db/test_models.py`**

Change line 1 of `tests/db/test_models.py`:

From: `from datetime import date, datetime, timezone`
To: `from datetime import date`

The `datetime` and `timezone` imports were never used in this test file.

- [ ] **Step 5: Create `tests/conftest.py` with shared fixtures**

Write to `tests/conftest.py`:

```python
"""Shared test fixtures for the entire suite.

Specific subdirectories may add their own conftest.py for narrower fixtures.
"""
from datetime import datetime

import pytest

from core.db import (
    Account,
    Base,
    Institution,
    Item,
    make_engine,
    make_session_factory,
)


@pytest.fixture
def engine(tmp_path):
    """A fresh in-temp-file SQLite engine with all tables created via metadata."""
    db_path = tmp_path / "test.db"
    eng = make_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    """A session bound to the per-test engine."""
    SessionLocal = make_session_factory(engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def seeded_chain(session):
    """Seed institution → item → account so per-test code can insert transactions/holdings.

    Returns a dict with the inserted instances:
        {"institution": Institution, "item": Item, "account": Account}

    The Item's access_token_ciphertext is a 28-byte placeholder
    (nonce(12) + 0-byte ct + tag(16)) suitable for tests that don't actually
    decrypt. Tests that need a real ciphertext should overwrite this column.
    """
    inst = Institution(
        institution_id="ins_test",
        name="Test Bank",
        primary_color="#000000",
    )
    item = Item(
        item_id="item_test",
        institution_id="ins_test",
        access_token_ciphertext=b"\x00" * 28,
        created_at=datetime(2026, 1, 1),
    )
    acct = Account(
        account_id="acc_test",
        item_id="item_test",
        name="Checking",
        type="depository",
        subtype="checking",
        current_balance=1000.00,
        iso_currency_code="USD",
    )
    session.add_all([inst, item, acct])
    session.commit()
    return {"institution": inst, "item": item, "account": acct}


@pytest.fixture
def fake_keychain(monkeypatch):
    """Replace the `keyring` backend used by core.crypto.keychain with an in-memory dict.

    Returns the backing dict so tests can inspect or pre-seed entries.
    """
    from core.crypto import keychain

    store: dict[tuple[str, str], str] = {}
    monkeypatch.setattr(
        keychain.keyring, "get_password", lambda s, a: store.get((s, a))
    )
    monkeypatch.setattr(
        keychain.keyring, "set_password",
        lambda s, a, p: store.__setitem__((s, a), p),
    )

    def fake_delete(service, account):
        if (service, account) not in store:
            import keyring.errors
            raise keyring.errors.PasswordDeleteError("not found")
        del store[(service, account)]
    monkeypatch.setattr(keychain.keyring, "delete_password", fake_delete)

    return store
```

Note: existing test files (`tests/db/test_session.py`, `tests/db/test_models.py`, `tests/crypto/test_keychain.py`, `tests/crypto/test_integration.py`) still define their own engine/session/fake_keychain fixtures inline. **Do not edit them.** The shared fixtures here are picked up automatically by pytest discovery and are available to *new* test files in Plan 2. Future cleanup can dedupe; not in scope for this task.

- [ ] **Step 6: Register the `sandbox` pytest marker in `pyproject.toml`**

In `pyproject.toml`, find `[tool.pytest.ini_options]` and replace it with:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "-ra --strict-markers"
markers = [
    "sandbox: tests that hit Plaid Sandbox over the network (requires PLAID_CLIENT_ID/PLAID_SECRET in env). Skipped by default; run with `pytest -m sandbox`.",
]
```

- [ ] **Step 7: Run the full suite — confirm nothing broke**

```bash
.venv/bin/pytest -v
```

Expected: 28 passed (same as Plan 1). The polish should be additive only.

- [ ] **Step 8: Commit**

```bash
git add core/db/__init__.py migrations/env.py tests/conftest.py \
        tests/db/test_migration.py tests/db/test_models.py pyproject.toml
git commit -m "chore: foundation polish for Plan 2 prereqs (db re-exports, DATABASE_URL env, shared fixtures, sandbox marker)"
```

---

## Task 2: Plaid client factory + env routing

**Files:**
- Modify: `pyproject.toml` (add `plaid-python` dep)
- Create: `core/plaid/__init__.py` (empty for now)
- Create: `core/plaid/client.py`
- Create: `tests/plaid/__init__.py` (empty)
- Create: `tests/plaid/test_client.py`

- [ ] **Step 1: Add plaid-python dependency**

In `pyproject.toml`, change the `dependencies` block under `[project]` to add `plaid-python`:

```toml
dependencies = [
    "sqlalchemy>=2.0,<3",
    "alembic>=1.13,<2",
    "cryptography>=42.0",
    "keyring>=25.0",
    "plaid-python>=24.0,<32",
]
```

- [ ] **Step 2: Reinstall the venv with the new dep**

```bash
.venv/bin/pip install -e ".[dev]"
```

Expected: `Successfully installed ... plaid-python-...`. Confirm:

```bash
.venv/bin/pip show plaid-python | head -2
```

Expected:
```
Name: plaid-python
Version: <some 24.x or higher>
```

- [ ] **Step 3: Create the empty plaid package**

```bash
mkdir -p core/plaid tests/plaid
touch core/plaid/__init__.py tests/plaid/__init__.py
```

- [ ] **Step 4: Write the failing test**

Write to `tests/plaid/test_client.py`:

```python
import pytest

from core.plaid.client import PlaidEnv, make_plaid_client


def test_make_plaid_client_returns_plaid_api_object():
    """The factory should return a usable PlaidApi instance, not a raw config."""
    client = make_plaid_client(env=PlaidEnv.SANDBOX, client_id="cid", secret="sec")
    # Must have the methods we'll actually call.
    assert hasattr(client, "link_token_create")
    assert hasattr(client, "item_public_token_exchange")
    assert hasattr(client, "transactions_sync")
    assert hasattr(client, "accounts_get")
    assert hasattr(client, "investments_holdings_get")


def test_make_plaid_client_routes_each_env_to_correct_host():
    """Each env should produce a client pointing at the matching Plaid host."""
    for env, expected_host in [
        (PlaidEnv.SANDBOX, "sandbox.plaid.com"),
        (PlaidEnv.DEVELOPMENT, "development.plaid.com"),
        (PlaidEnv.PRODUCTION, "production.plaid.com"),
    ]:
        client = make_plaid_client(env=env, client_id="cid", secret="sec")
        # The host is on the underlying api_client.configuration.host.
        host = client.api_client.configuration.host
        assert expected_host in host, f"env={env} produced host {host}"


def test_invalid_env_string_raises():
    with pytest.raises(ValueError):
        PlaidEnv("not_a_real_env")
```

- [ ] **Step 5: Run test to confirm it fails**

```bash
.venv/bin/pytest tests/plaid/test_client.py -v
```

Expected: ImportError on `core.plaid.client`.

- [ ] **Step 6: Implement `core/plaid/client.py`**

Write to `core/plaid/client.py`:

```python
"""Plaid client factory — env-aware wrapper around plaid-python's PlaidApi.

Usage:
    from core.plaid.client import PlaidEnv, make_plaid_client
    client = make_plaid_client(
        env=PlaidEnv.SANDBOX,
        client_id=os.environ["PLAID_CLIENT_ID"],
        secret=os.environ["PLAID_SECRET"],
    )
    response = client.link_token_create(request)
"""
from enum import Enum

import plaid
from plaid.api import plaid_api


class PlaidEnv(str, Enum):
    """Plaid environments. The user's Development env is what the app uses in production."""

    SANDBOX = "sandbox"
    DEVELOPMENT = "development"
    PRODUCTION = "production"


_HOSTS: dict[PlaidEnv, str] = {
    PlaidEnv.SANDBOX: plaid.Environment.Sandbox,
    PlaidEnv.DEVELOPMENT: plaid.Environment.Development,
    PlaidEnv.PRODUCTION: plaid.Environment.Production,
}


def make_plaid_client(
    *, env: PlaidEnv, client_id: str, secret: str
) -> plaid_api.PlaidApi:
    """Create a configured PlaidApi instance for the given environment."""
    configuration = plaid.Configuration(
        host=_HOSTS[env],
        api_key={
            "clientId": client_id,
            "secret": secret,
        },
    )
    api_client = plaid.ApiClient(configuration)
    return plaid_api.PlaidApi(api_client)
```

- [ ] **Step 7: Run tests to confirm pass**

```bash
.venv/bin/pytest tests/plaid/test_client.py -v
```

Expected: 3 passed.

If `plaid.Environment.Development` raises `AttributeError` (the field has been deprecated in some plaid-python versions), substitute the string URLs directly:

```python
_HOSTS: dict[PlaidEnv, str] = {
    PlaidEnv.SANDBOX: "https://sandbox.plaid.com",
    PlaidEnv.DEVELOPMENT: "https://development.plaid.com",
    PlaidEnv.PRODUCTION: "https://production.plaid.com",
}
```

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml core/plaid/__init__.py core/plaid/client.py \
        tests/plaid/__init__.py tests/plaid/test_client.py
git commit -m "feat(plaid): client factory with env routing (Plan 2, Task 2)"
```

---

## Task 3: Token storage helpers (encrypt+persist / load+decrypt)

**Files:**
- Create: `core/plaid/tokens.py`
- Create: `tests/plaid/test_tokens.py`

This is a thin layer that bridges `core.crypto` and the `Item` row. Plan 2's link/sync flows call into it; Plan 1's modules don't change.

- [ ] **Step 1: Write the failing test**

Write to `tests/plaid/test_tokens.py`:

```python
import pytest
from sqlalchemy import select

from core.crypto import get_or_create_master_key
from core.db import Item
from core.plaid.tokens import load_decrypted_token, store_encrypted_token


def test_store_then_load_round_trip(session, seeded_chain, fake_keychain):
    """store_encrypted_token writes encrypted bytes; load_decrypted_token returns plaintext."""
    item = seeded_chain["item"]
    store_encrypted_token(session, item_id=item.item_id, access_token="access-sandbox-xyz")
    session.commit()

    plaintext = load_decrypted_token(session, item_id=item.item_id)
    assert plaintext == "access-sandbox-xyz"


def test_store_replaces_previous_ciphertext(session, seeded_chain, fake_keychain):
    """A second store call for the same item_id overwrites the first ciphertext."""
    item = seeded_chain["item"]
    store_encrypted_token(session, item_id=item.item_id, access_token="first")
    session.commit()
    store_encrypted_token(session, item_id=item.item_id, access_token="second")
    session.commit()

    assert load_decrypted_token(session, item_id=item.item_id) == "second"


def test_load_for_unknown_item_raises(session, fake_keychain):
    with pytest.raises(LookupError):
        load_decrypted_token(session, item_id="item_does_not_exist")


def test_ciphertext_is_actually_encrypted(session, seeded_chain, fake_keychain):
    """The ciphertext column should not contain the plaintext."""
    item = seeded_chain["item"]
    store_encrypted_token(session, item_id=item.item_id, access_token="access-sandbox-xyz")
    session.commit()

    fetched = session.scalar(select(Item).where(Item.item_id == item.item_id))
    assert b"access-sandbox-xyz" not in fetched.access_token_ciphertext
    assert len(fetched.access_token_ciphertext) >= 12 + 16  # nonce + tag minimum


def test_aad_binding_to_item_id(session, seeded_chain, fake_keychain):
    """A ciphertext stored for one item_id cannot be decrypted under another."""
    item = seeded_chain["item"]
    store_encrypted_token(session, item_id=item.item_id, access_token="real-token")
    session.commit()

    # Manually copy the ciphertext to a new item with a different id.
    other_item = Item(
        item_id="item_other",
        institution_id="ins_test",
        access_token_ciphertext=item.access_token_ciphertext,
    )
    session.add(other_item)
    session.commit()

    from cryptography.exceptions import InvalidTag

    with pytest.raises(InvalidTag):
        load_decrypted_token(session, item_id="item_other")
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
.venv/bin/pytest tests/plaid/test_tokens.py -v
```

Expected: ImportError on `core.plaid.tokens`.

- [ ] **Step 3: Implement `core/plaid/tokens.py`**

Write to `core/plaid/tokens.py`:

```python
"""Glue between `core.crypto` and the `Item` row.

Public API:
- store_encrypted_token(session, item_id, access_token) -> None
- load_decrypted_token(session, item_id) -> str

Both call into `core.crypto.get_or_create_master_key()` which reads from
the macOS Keychain (or the test fake_keychain fixture).
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.crypto import decrypt_token, encrypt_token, get_or_create_master_key
from core.db import Item


def store_encrypted_token(session: Session, *, item_id: str, access_token: str) -> None:
    """Encrypt `access_token` and store on the Item row identified by `item_id`.

    The Item row must already exist (Link's exchange step inserts the row first,
    THEN populates the ciphertext via this function — keeping the encryption
    logic out of the model layer). The session is NOT committed here; caller commits.
    """
    item = session.scalar(select(Item).where(Item.item_id == item_id))
    if item is None:
        raise LookupError(f"Item not found: {item_id}")
    key = get_or_create_master_key()
    item.access_token_ciphertext = encrypt_token(access_token, key, item_id=item_id)


def load_decrypted_token(session: Session, *, item_id: str) -> str:
    """Read the Item's ciphertext, decrypt, and return the plaintext access token."""
    item = session.scalar(select(Item).where(Item.item_id == item_id))
    if item is None:
        raise LookupError(f"Item not found: {item_id}")
    key = get_or_create_master_key()
    return decrypt_token(item.access_token_ciphertext, key, item_id=item_id)
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
.venv/bin/pytest tests/plaid/test_tokens.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add core/plaid/tokens.py tests/plaid/test_tokens.py
git commit -m "feat(plaid): encrypt/decrypt access tokens via Item row (Plan 2, Task 3)"
```

---

## Task 4: Plaid error mapping

**Files:**
- Create: `core/plaid/errors.py`
- Create: `tests/plaid/test_errors.py`

This is a pure function — Plaid `ApiException` (or just the response error_code string) → `(status, error_message)` tuple per the design's table. Keeping it in its own module so sync.py and refresh.py both depend on it cleanly.

- [ ] **Step 1: Write the failing test**

Write to `tests/plaid/test_errors.py`:

```python
import pytest

from core.plaid.errors import (
    SyncOutcome,
    classify_plaid_error,
    is_retryable,
)


def test_item_login_required_classifies_as_relink_required():
    outcome = classify_plaid_error("ITEM_LOGIN_REQUIRED", "the message")
    assert outcome.status == "error"
    assert outcome.user_action == "relink"
    assert "ITEM_LOGIN_REQUIRED" in outcome.error


def test_institution_down_classifies_as_transient():
    outcome = classify_plaid_error("INSTITUTION_DOWN", "down for maintenance")
    assert outcome.status == "error"
    assert outcome.user_action is None  # not user-actionable
    assert is_retryable("INSTITUTION_DOWN")


def test_product_not_ready_is_retryable():
    assert is_retryable("PRODUCT_NOT_READY")


def test_rate_limit_is_retryable():
    assert is_retryable("RATE_LIMIT_EXCEEDED")


def test_invalid_access_token_classifies_as_relink_required():
    outcome = classify_plaid_error("INVALID_ACCESS_TOKEN", "")
    assert outcome.user_action == "relink"


def test_unknown_code_is_classified_as_generic_error_not_retryable():
    outcome = classify_plaid_error("SOMETHING_NEW_PLAID_ADDED", "details")
    assert outcome.status == "error"
    assert "SOMETHING_NEW_PLAID_ADDED" in outcome.error
    assert outcome.user_action is None
    assert is_retryable("SOMETHING_NEW_PLAID_ADDED") is False
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
.venv/bin/pytest tests/plaid/test_errors.py -v
```

Expected: ImportError on `core.plaid.errors`.

- [ ] **Step 3: Implement `core/plaid/errors.py`**

Write to `core/plaid/errors.py`:

```python
"""Map Plaid `error_code` strings to sync outcomes.

Source of truth for the error → behavior table in
docs/superpowers/specs/2026-04-26-finance-tracker-design.md (section 7.2).
"""
from dataclasses import dataclass
from typing import Literal, Optional

# Codes the sync engine should retry within a single run (with backoff).
_RETRYABLE_CODES = {
    "PRODUCT_NOT_READY",
    "RATE_LIMIT_EXCEEDED",
    "INSTITUTION_DOWN",
    "INSTITUTION_NOT_RESPONDING",
}

# Codes that mean the user must re-link via Plaid Link in update mode.
_RELINK_REQUIRED_CODES = {
    "ITEM_LOGIN_REQUIRED",
    "INVALID_ACCESS_TOKEN",
    "INVALID_CREDENTIALS",
}


@dataclass(frozen=True)
class SyncOutcome:
    """Result of classifying a Plaid error.

    status: value to write into items.last_sync_status ('ok' | 'error' | 'pending').
    error: human-readable string for items.last_sync_error.
    user_action: 'relink' if the user must re-authenticate, None otherwise.
    """

    status: Literal["ok", "error", "pending"]
    error: str
    user_action: Optional[Literal["relink"]]


def classify_plaid_error(error_code: str, error_message: str) -> SyncOutcome:
    """Classify a Plaid error code → SyncOutcome.

    All non-success codes map to status='error'. The `user_action` field
    drives UI: 'relink' shows the user a Reconnect button.
    """
    user_action: Optional[Literal["relink"]] = None
    if error_code in _RELINK_REQUIRED_CODES:
        user_action = "relink"
    return SyncOutcome(
        status="error",
        error=f"{error_code}: {error_message}",
        user_action=user_action,
    )


def is_retryable(error_code: str) -> bool:
    """True if the sync engine should retry within the current run (with backoff)."""
    return error_code in _RETRYABLE_CODES
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
.venv/bin/pytest tests/plaid/test_errors.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add core/plaid/errors.py tests/plaid/test_errors.py
git commit -m "feat(plaid): error-code classification (Plan 2, Task 4)"
```

---

## Task 5: Link flow — create_link_token + exchange_public_token

**Files:**
- Create: `core/plaid/link.py`
- Create: `tests/plaid/conftest.py` (fake Plaid client fixture)
- Create: `tests/plaid/test_link.py`

- [ ] **Step 1: Create `tests/plaid/conftest.py` with the fake client fixture**

Write to `tests/plaid/conftest.py`:

```python
"""Plaid-specific test fixtures — fake_client, canned response builders."""
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def fake_plaid_client():
    """A MagicMock standing in for plaid.api.plaid_api.PlaidApi.

    Each test sets up the methods it needs:
        fake_plaid_client.link_token_create.return_value = SomeResponse(...)

    The mock auto-attribute-generates every plaid-python method, so calling
    `fake_plaid_client.transactions_sync(req)` returns a MagicMock unless
    .return_value is set.
    """
    return MagicMock(name="fake_plaid_client")


def _wrap(payload: dict) -> MagicMock:
    """Wrap a dict so `.to_dict()` and attribute access both work, mirroring
    plaid-python's response objects."""
    obj = MagicMock()
    obj.to_dict.return_value = payload
    for key, value in payload.items():
        setattr(obj, key, value)
    return obj


@pytest.fixture
def make_response():
    """Return a helper that wraps a dict into a plaid-response-shaped MagicMock."""
    return _wrap
```

- [ ] **Step 2: Write the failing test**

Write to `tests/plaid/test_link.py`:

```python
from sqlalchemy import select

from core.db import Account, Institution, Item
from core.plaid.link import create_link_token, exchange_public_token
from core.plaid.tokens import load_decrypted_token


def test_create_link_token_calls_plaid_and_returns_token(
    fake_plaid_client, make_response
):
    fake_plaid_client.link_token_create.return_value = make_response(
        {"link_token": "link-sandbox-12345", "expiration": "2026-04-27T00:00:00Z"}
    )

    token = create_link_token(
        client=fake_plaid_client,
        client_user_id="local-user",
    )
    assert token == "link-sandbox-12345"
    fake_plaid_client.link_token_create.assert_called_once()


def test_exchange_public_token_persists_item_institution_accounts(
    fake_plaid_client, make_response, session, fake_keychain
):
    # Plaid's /item/public_token/exchange returns access_token + item_id.
    fake_plaid_client.item_public_token_exchange.return_value = make_response(
        {"access_token": "access-sandbox-xyz", "item_id": "item_NEW"}
    )
    # Plaid's /accounts/get returns the institution_id + accounts list.
    fake_plaid_client.accounts_get.return_value = make_response(
        {
            "item": {"item_id": "item_NEW", "institution_id": "ins_wf"},
            "accounts": [
                {
                    "account_id": "acc_NEW_1",
                    "name": "Plaid Checking",
                    "official_name": "Wells Premier Checking",
                    "type": "depository",
                    "subtype": "checking",
                    "mask": "0000",
                    "balances": {
                        "current": 1234.56,
                        "available": 1234.56,
                        "limit": None,
                        "iso_currency_code": "USD",
                    },
                },
                {
                    "account_id": "acc_NEW_2",
                    "name": "Plaid Savings",
                    "official_name": None,
                    "type": "depository",
                    "subtype": "savings",
                    "mask": "1111",
                    "balances": {
                        "current": 5000.00,
                        "available": 5000.00,
                        "limit": None,
                        "iso_currency_code": "USD",
                    },
                },
            ],
        }
    )
    # Plaid's /institutions/get_by_id returns metadata for the bank.
    fake_plaid_client.institutions_get_by_id.return_value = make_response(
        {
            "institution": {
                "institution_id": "ins_wf",
                "name": "Wells Fargo",
                "primary_color": "#d71e28",
                "url": "https://wellsfargo.com",
                "logo": None,
            }
        }
    )

    item_id = exchange_public_token(
        client=fake_plaid_client,
        session=session,
        public_token="public-sandbox-pub",
    )
    assert item_id == "item_NEW"

    # Confirm rows landed.
    inst = session.scalar(select(Institution).where(Institution.institution_id == "ins_wf"))
    assert inst.name == "Wells Fargo"

    item = session.scalar(select(Item).where(Item.item_id == "item_NEW"))
    assert item.institution_id == "ins_wf"
    # Token was encrypted and stored — we can decrypt it back.
    assert load_decrypted_token(session, item_id="item_NEW") == "access-sandbox-xyz"

    accounts = session.scalars(select(Account).where(Account.item_id == "item_NEW")).all()
    assert len(accounts) == 2
    a1 = next(a for a in accounts if a.account_id == "acc_NEW_1")
    assert a1.name == "Plaid Checking"
    assert a1.official_name == "Wells Premier Checking"
    assert a1.current_balance == 1234.56
    assert a1.subtype == "checking"
    assert a1.iso_currency_code == "USD"


def test_exchange_does_not_create_duplicate_institution(
    fake_plaid_client, make_response, session, seeded_chain, fake_keychain
):
    """If the institution already exists (from a prior link), reuse it."""
    fake_plaid_client.item_public_token_exchange.return_value = make_response(
        {"access_token": "access-sandbox-xyz", "item_id": "item_NEW2"}
    )
    fake_plaid_client.accounts_get.return_value = make_response(
        {
            "item": {"item_id": "item_NEW2", "institution_id": "ins_test"},
            "accounts": [
                {
                    "account_id": "acc_NEW2_1",
                    "name": "Other Checking",
                    "official_name": None,
                    "type": "depository",
                    "subtype": "checking",
                    "mask": "2222",
                    "balances": {
                        "current": 100.0,
                        "available": 100.0,
                        "limit": None,
                        "iso_currency_code": "USD",
                    },
                },
            ],
        }
    )
    # institutions_get_by_id should NOT be called when the row already exists,
    # but the implementation may call it idempotently — either is fine. We
    # don't assert on it.

    exchange_public_token(
        client=fake_plaid_client,
        session=session,
        public_token="public-sandbox-pub",
    )

    institutions = session.scalars(select(Institution)).all()
    # ins_test from seeded_chain + (no new ins, since institution_id matches)
    assert len(institutions) == 1
    assert institutions[0].institution_id == "ins_test"
```

- [ ] **Step 3: Run test to confirm it fails**

```bash
.venv/bin/pytest tests/plaid/test_link.py -v
```

Expected: ImportError on `core.plaid.link`.

- [ ] **Step 4: Implement `core/plaid/link.py`**

Write to `core/plaid/link.py`:

```python
"""Plaid Link flow: create link_token, exchange public_token → access_token, persist Item.

The Link iframe runs in the user's browser (frontend) and posts the public_token
to our /plaid/exchange endpoint, which calls exchange_public_token here.

Public API:
- create_link_token(client, *, client_user_id) -> str
- exchange_public_token(client, session, *, public_token) -> str  (returns item_id)
"""
from datetime import datetime, timezone
from typing import Any

from plaid.api.plaid_api import PlaidApi
from plaid.model.country_code import CountryCode
from plaid.model.institutions_get_by_id_request import InstitutionsGetByIdRequest
from plaid.model.item_public_token_exchange_request import (
    ItemPublicTokenExchangeRequest,
)
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products
from plaid.model.accounts_get_request import AccountsGetRequest
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import Account, Institution, Item
from core.plaid.tokens import store_encrypted_token


_PRODUCTS = [Products("transactions"), Products("investments")]
_COUNTRY_CODES = [CountryCode("US")]


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def create_link_token(client: PlaidApi, *, client_user_id: str) -> str:
    """Ask Plaid for a short-lived Link token. The frontend uses it to open the iframe."""
    request = LinkTokenCreateRequest(
        products=_PRODUCTS,
        client_name="Finance Tracker",
        country_codes=_COUNTRY_CODES,
        language="en",
        user=LinkTokenCreateRequestUser(client_user_id=client_user_id),
    )
    response = client.link_token_create(request)
    return response.link_token


def exchange_public_token(
    client: PlaidApi,
    session: Session,
    *,
    public_token: str,
) -> str:
    """Exchange a short-lived public_token for a long-lived access_token, encrypt it,
    and persist the Item, Institution, and initial Accounts. Returns item_id.

    The session is committed only after every row is written. On any failure mid-way,
    nothing is persisted.
    """
    # 1. public_token → access_token + item_id
    exchange_resp = client.item_public_token_exchange(
        ItemPublicTokenExchangeRequest(public_token=public_token)
    )
    access_token = exchange_resp.access_token
    item_id = exchange_resp.item_id

    # 2. /accounts/get → institution_id + initial accounts
    accounts_resp = client.accounts_get(AccountsGetRequest(access_token=access_token))
    accounts_resp_dict = accounts_resp.to_dict()
    institution_id = accounts_resp_dict["item"]["institution_id"]
    accounts_payload = accounts_resp_dict["accounts"]

    # 3. Upsert Institution (lookup if missing).
    inst = session.scalar(
        select(Institution).where(Institution.institution_id == institution_id)
    )
    if inst is None:
        inst = _fetch_and_build_institution(client, institution_id)
        session.add(inst)

    # 4. Insert Item with placeholder ciphertext (we'll overwrite after add).
    now = _utcnow_naive()
    item = Item(
        item_id=item_id,
        institution_id=institution_id,
        access_token_ciphertext=b"\x00" * 28,  # placeholder, replaced below
        last_sync_at=None,
        last_sync_status="pending",
        last_sync_error=None,
        created_at=now,
    )
    session.add(item)
    session.flush()  # so the Item is queryable by store_encrypted_token

    # 5. Encrypt the access token onto the just-inserted Item row.
    store_encrypted_token(session, item_id=item_id, access_token=access_token)

    # 6. Insert all accounts.
    for acct_payload in accounts_payload:
        balances = acct_payload.get("balances") or {}
        session.add(
            Account(
                account_id=acct_payload["account_id"],
                item_id=item_id,
                name=acct_payload.get("name") or "",
                official_name=acct_payload.get("official_name"),
                type=str(acct_payload.get("type")),
                subtype=str(acct_payload.get("subtype")) if acct_payload.get("subtype") else None,
                mask=acct_payload.get("mask"),
                current_balance=balances.get("current"),
                available_balance=balances.get("available"),
                limit_balance=balances.get("limit"),
                iso_currency_code=balances.get("iso_currency_code"),
                last_balance_at=now,
                raw_payload=acct_payload,
            )
        )

    session.commit()
    return item_id


def _fetch_and_build_institution(client: PlaidApi, institution_id: str) -> Institution:
    """Call /institutions/get_by_id and shape the response into an Institution row."""
    resp = client.institutions_get_by_id(
        InstitutionsGetByIdRequest(
            institution_id=institution_id,
            country_codes=_COUNTRY_CODES,
        )
    )
    payload: dict[str, Any] = resp.to_dict()["institution"]
    return Institution(
        institution_id=payload["institution_id"],
        name=payload.get("name") or "",
        logo=payload.get("logo"),
        primary_color=payload.get("primary_color"),
        url=payload.get("url"),
    )
```

- [ ] **Step 5: Run tests to confirm pass**

```bash
.venv/bin/pytest tests/plaid/test_link.py -v
```

Expected: 3 passed.

If the plaid-python model classes have moved (a common version drift), the failures will be `ImportError` from the imports at the top of `link.py`. Map them to the actual location in your installed plaid-python — `pip show -f plaid-python | grep model` will list available models. Update the imports in `link.py` only; the function bodies are stable.

- [ ] **Step 6: Commit**

```bash
git add core/plaid/link.py tests/plaid/conftest.py tests/plaid/test_link.py
git commit -m "feat(plaid): link token create + public_token exchange (Plan 2, Task 5)"
```

---

## Task 6: apply_sync_page — single-page atomicity

**Files:**
- Create: `core/plaid/sync.py` (initial skeleton with `apply_sync_page` only — `sync_transactions` added in Task 7)
- Create: `tests/plaid/test_sync.py`

This is the most load-bearing function in Plan 2. The invariant: the cursor advances if and only if every row in the page commits. If the function raises, the cursor stays unchanged and the next sync replays the page idempotently.

- [ ] **Step 1: Write the failing test**

Write to `tests/plaid/test_sync.py`:

```python
from datetime import date, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from core.db import Item, Transaction
from core.plaid.sync import apply_sync_page


# ---------- helpers ----------------------------------------------------------


def _txn(transaction_id: str, account_id: str = "acc_test", amount: float = 10.0, **kw):
    """Build a Plaid-shaped transaction dict (matches what /transactions/sync returns)."""
    base = {
        "transaction_id": transaction_id,
        "account_id": account_id,
        "date": "2026-04-20",
        "authorized_date": None,
        "amount": amount,
        "iso_currency_code": "USD",
        "name": "TEST TXN",
        "merchant_name": "Test Merchant",
        "payment_channel": "in store",
        "pending": False,
        "personal_finance_category": {
            "primary": "FOOD_AND_DRINK",
            "detailed": "FOOD_AND_DRINK_GROCERIES",
            "confidence_level": "VERY_HIGH",
        },
        "counterparties": [],
        "location": {},
        "payment_meta": {},
    }
    base.update(kw)
    return base


def _page(*, added=None, modified=None, removed=None, has_more=False, next_cursor="c1"):
    return SimpleNamespace(
        added=added or [],
        modified=modified or [],
        removed=removed or [],  # list of {"transaction_id": "..."}
        has_more=has_more,
        next_cursor=next_cursor,
    )


# ---------- happy paths ------------------------------------------------------


def test_apply_page_inserts_added_transactions(session, seeded_chain):
    page = _page(added=[_txn("txn_1"), _txn("txn_2")])
    apply_sync_page(session, item_id=seeded_chain["item"].item_id, page=page)
    session.commit()

    txns = session.scalars(select(Transaction)).all()
    assert {t.transaction_id for t in txns} == {"txn_1", "txn_2"}
    assert txns[0].category_primary == "FOOD_AND_DRINK"
    assert txns[0].category_detailed == "FOOD_AND_DRINK_GROCERIES"
    assert txns[0].category_confidence == "VERY_HIGH"


def test_apply_page_overwrites_modified_transactions(session, seeded_chain):
    page1 = _page(added=[_txn("txn_1", amount=10.0, name="OLD")])
    apply_sync_page(session, item_id=seeded_chain["item"].item_id, page=page1)
    session.commit()

    page2 = _page(modified=[_txn("txn_1", amount=99.99, name="NEW")])
    apply_sync_page(session, item_id=seeded_chain["item"].item_id, page=page2)
    session.commit()

    txn = session.scalar(select(Transaction).where(Transaction.transaction_id == "txn_1"))
    assert txn.amount == 99.99
    assert txn.name == "NEW"


def test_apply_page_soft_deletes_removed_transactions(session, seeded_chain):
    page1 = _page(added=[_txn("txn_1")])
    apply_sync_page(session, item_id=seeded_chain["item"].item_id, page=page1)
    session.commit()

    page2 = _page(removed=[{"transaction_id": "txn_1"}])
    apply_sync_page(session, item_id=seeded_chain["item"].item_id, page=page2)
    session.commit()

    txn = session.scalar(select(Transaction).where(Transaction.transaction_id == "txn_1"))
    assert txn is not None  # row stays
    assert txn.removed_at is not None  # soft-delete


def test_apply_page_advances_cursor_and_last_sync_at(session, seeded_chain):
    page = _page(added=[_txn("txn_1")], next_cursor="cursor_xyz")
    before = datetime.utcnow()
    apply_sync_page(session, item_id=seeded_chain["item"].item_id, page=page)
    session.commit()

    item = session.scalar(select(Item).where(Item.item_id == seeded_chain["item"].item_id))
    assert item.transactions_cursor == "cursor_xyz"
    assert item.last_sync_at is not None
    assert item.last_sync_at >= before


# ---------- atomicity --------------------------------------------------------


def test_failure_mid_apply_does_not_advance_cursor(session, seeded_chain):
    """If apply_sync_page raises, the caller's transaction rolls back: no cursor change."""
    # Two adds: the first is fine; the second references a non-existent account, so
    # the FK insert will fail at flush/commit. We expect:
    #  - The caller's session.commit() raises.
    #  - The cursor remains None (its initial value).
    #  - Neither transaction is committed.
    item_id = seeded_chain["item"].item_id

    bad_page = _page(
        added=[
            _txn("txn_good", account_id="acc_test"),
            _txn("txn_bad", account_id="acc_does_not_exist"),
        ],
        next_cursor="should_not_persist",
    )
    apply_sync_page(session, item_id=item_id, page=bad_page)
    with pytest.raises(Exception):
        session.commit()
    session.rollback()

    item = session.scalar(select(Item).where(Item.item_id == item_id))
    assert item.transactions_cursor is None
    assert session.scalar(select(Transaction)) is None


def test_replaying_a_page_is_idempotent(session, seeded_chain):
    """Apply the same page twice — end state identical to applying once."""
    item_id = seeded_chain["item"].item_id
    page = _page(added=[_txn("txn_1", amount=42.0)])

    apply_sync_page(session, item_id=item_id, page=page)
    session.commit()
    apply_sync_page(session, item_id=item_id, page=page)
    session.commit()

    txns = session.scalars(select(Transaction)).all()
    assert len(txns) == 1
    assert txns[0].amount == 42.0


# ---------- per-item isolation -----------------------------------------------


def test_apply_for_one_item_does_not_touch_another_item(session, seeded_chain):
    """Adding a second item + transactions should not affect the first item's cursor."""
    from core.db import Account, Item

    other = Item(
        item_id="item_other",
        institution_id="ins_test",
        access_token_ciphertext=b"\x00" * 28,
        transactions_cursor="other_existing_cursor",
    )
    other_acct = Account(
        account_id="acc_other",
        item_id="item_other",
        name="Other Checking",
        type="depository",
        subtype="checking",
    )
    session.add_all([other, other_acct])
    session.commit()

    page = _page(
        added=[_txn("txn_for_other", account_id="acc_other")],
        next_cursor="new_first_cursor",
    )
    apply_sync_page(session, item_id="item_other", page=page)
    session.commit()

    first_item = session.scalar(select(Item).where(Item.item_id == seeded_chain["item"].item_id))
    other_item = session.scalar(select(Item).where(Item.item_id == "item_other"))
    assert first_item.transactions_cursor is None
    assert other_item.transactions_cursor == "new_first_cursor"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
.venv/bin/pytest tests/plaid/test_sync.py -v
```

Expected: ImportError on `core.plaid.sync`.

- [ ] **Step 3: Implement `core/plaid/sync.py` (apply_sync_page only)**

Write to `core/plaid/sync.py`:

```python
"""Transactions sync engine.

This module implements the cursor-atomicity invariant from spec section 7.3:
the cursor advances if and only if every row in the page is persisted.
The caller is responsible for the surrounding `session.commit()` so the cursor
write and the row writes share a single SQL transaction.
"""
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import Item, Transaction


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_date(value: Any) -> date | None:
    """Plaid returns ISO date strings; sometimes datetime.date instances."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise TypeError(f"Cannot parse date from {value!r}")


def _txn_columns_from_payload(item_id: str, payload: dict) -> dict:
    """Map a Plaid transaction dict → keyword args for the Transaction model."""
    pfc = payload.get("personal_finance_category") or {}
    return {
        "transaction_id": payload["transaction_id"],
        "account_id": payload["account_id"],
        "date": _parse_date(payload.get("date")),
        "authorized_date": _parse_date(payload.get("authorized_date")),
        "amount": float(payload.get("amount", 0.0)),
        "iso_currency_code": payload.get("iso_currency_code"),
        "name": payload.get("name") or "",
        "merchant_name": payload.get("merchant_name"),
        "payment_channel": payload.get("payment_channel"),
        "pending": bool(payload.get("pending", False)),
        "category_primary": pfc.get("primary"),
        "category_detailed": pfc.get("detailed"),
        "category_confidence": pfc.get("confidence_level"),
        "raw_payload": payload,
    }


def apply_sync_page(session: Session, *, item_id: str, page: Any) -> None:
    """Apply a single page from /transactions/sync.

    `page` must have attributes: `added` (list of dicts), `modified` (list of dicts),
    `removed` (list of dicts each with `transaction_id`), `has_more` (bool),
    `next_cursor` (str). plaid-python's response object satisfies this; tests can
    pass a SimpleNamespace.

    DOES NOT call session.commit() — the caller is responsible. This lets the
    cursor write share an SQL transaction with the row writes (atomicity).
    """
    item = session.scalar(select(Item).where(Item.item_id == item_id))
    if item is None:
        raise LookupError(f"Item not found: {item_id}")

    now = _utcnow_naive()

    # 1. Added: insert as new rows, or revive a soft-deleted row if the same id exists.
    for payload in page.added:
        cols = _txn_columns_from_payload(item_id, payload)
        existing = session.scalar(
            select(Transaction).where(Transaction.transaction_id == cols["transaction_id"])
        )
        if existing is None:
            session.add(Transaction(**cols, created_at=now, updated_at=now))
        else:
            # Idempotent replay: if a previous run added this txn, just update.
            for k, v in cols.items():
                setattr(existing, k, v)
            existing.removed_at = None
            existing.updated_at = now

    # 2. Modified: same as added but the row is expected to exist.
    for payload in page.modified:
        cols = _txn_columns_from_payload(item_id, payload)
        existing = session.scalar(
            select(Transaction).where(Transaction.transaction_id == cols["transaction_id"])
        )
        if existing is None:
            # Plaid sent a "modified" for a row we don't have — treat as added.
            session.add(Transaction(**cols, created_at=now, updated_at=now))
        else:
            for k, v in cols.items():
                setattr(existing, k, v)
            existing.updated_at = now

    # 3. Removed: soft-delete (preserve the row).
    for payload in page.removed:
        existing = session.scalar(
            select(Transaction).where(Transaction.transaction_id == payload["transaction_id"])
        )
        if existing is not None and existing.removed_at is None:
            existing.removed_at = now
            existing.updated_at = now

    # 4. Advance cursor + sync timestamp on the Item row, in the same SQL transaction.
    item.transactions_cursor = page.next_cursor
    item.last_sync_at = now
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
.venv/bin/pytest tests/plaid/test_sync.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add core/plaid/sync.py tests/plaid/test_sync.py
git commit -m "feat(plaid): apply_sync_page with cursor atomicity (Plan 2, Task 6)"
```

---

## Task 7: sync_transactions — multi-page loop with retries

**Files:**
- Modify: `core/plaid/sync.py` (append `sync_transactions`)
- Modify: `tests/plaid/test_sync.py` (append multi-page + error tests)

- [ ] **Step 1: Append failing tests to `tests/plaid/test_sync.py`**

Append the following at the end of `tests/plaid/test_sync.py`:

```python
# ============================================================================
# sync_transactions (multi-page) tests
# ============================================================================
from unittest.mock import MagicMock

from core.plaid.sync import sync_transactions
from plaid.exceptions import ApiException


def _wrap_page(payload: dict) -> MagicMock:
    obj = MagicMock()
    obj.to_dict.return_value = payload
    for key, value in payload.items():
        setattr(obj, key, value)
    return obj


def test_sync_transactions_loops_until_has_more_false(
    session, seeded_chain, fake_plaid_client
):
    """Three-page response — all 3 pages applied, final cursor is the last next_cursor."""
    fake_plaid_client.transactions_sync.side_effect = [
        _wrap_page(
            {
                "added": [_txn("p1_txn1")],
                "modified": [],
                "removed": [],
                "has_more": True,
                "next_cursor": "c1",
            }
        ),
        _wrap_page(
            {
                "added": [_txn("p2_txn1"), _txn("p2_txn2")],
                "modified": [],
                "removed": [],
                "has_more": True,
                "next_cursor": "c2",
            }
        ),
        _wrap_page(
            {
                "added": [_txn("p3_txn1")],
                "modified": [],
                "removed": [],
                "has_more": False,
                "next_cursor": "c3_final",
            }
        ),
    ]

    sync_transactions(
        client=fake_plaid_client,
        session=session,
        item_id=seeded_chain["item"].item_id,
        access_token="access-sandbox-xyz",
    )

    txns = session.scalars(select(Transaction)).all()
    assert {t.transaction_id for t in txns} == {"p1_txn1", "p2_txn1", "p2_txn2", "p3_txn1"}

    item = session.scalar(select(Item).where(Item.item_id == seeded_chain["item"].item_id))
    assert item.transactions_cursor == "c3_final"
    assert item.last_sync_status == "ok"
    assert item.last_sync_error is None


def test_sync_transactions_passes_cursor_from_item_on_first_call(
    session, seeded_chain, fake_plaid_client
):
    """If the Item already has a cursor, /transactions/sync is called with it."""
    item = seeded_chain["item"]
    item.transactions_cursor = "saved_cursor_from_last_run"
    session.commit()

    fake_plaid_client.transactions_sync.return_value = _wrap_page(
        {
            "added": [],
            "modified": [],
            "removed": [],
            "has_more": False,
            "next_cursor": "saved_cursor_from_last_run",
        }
    )

    sync_transactions(
        client=fake_plaid_client,
        session=session,
        item_id=item.item_id,
        access_token="access-sandbox-xyz",
    )

    # The first call's request body included the saved cursor.
    first_call = fake_plaid_client.transactions_sync.call_args_list[0]
    request = first_call.args[0]
    # The plaid request object exposes .cursor as an attr.
    assert request.cursor == "saved_cursor_from_last_run"


def test_sync_transactions_classifies_plaid_error_and_does_not_advance(
    session, seeded_chain, fake_plaid_client
):
    """A Plaid ApiException for a non-retryable code marks the Item error and re-raises."""
    api_exc = ApiException(status=400)
    api_exc.body = '{"error_code": "ITEM_LOGIN_REQUIRED", "error_message": "relink please"}'
    fake_plaid_client.transactions_sync.side_effect = api_exc

    with pytest.raises(ApiException):
        sync_transactions(
            client=fake_plaid_client,
            session=session,
            item_id=seeded_chain["item"].item_id,
            access_token="access-sandbox-xyz",
        )

    # The implementation should have committed the error status before re-raising.
    session.expire_all()
    item = session.scalar(select(Item).where(Item.item_id == seeded_chain["item"].item_id))
    assert item.last_sync_status == "error"
    assert "ITEM_LOGIN_REQUIRED" in (item.last_sync_error or "")


def test_sync_transactions_retries_product_not_ready(
    session, seeded_chain, fake_plaid_client, monkeypatch
):
    """PRODUCT_NOT_READY first → succeeds on retry. The monkeypatched sleep keeps the test fast."""
    api_exc = ApiException(status=400)
    api_exc.body = '{"error_code": "PRODUCT_NOT_READY", "error_message": "still backfilling"}'

    success_page = _wrap_page(
        {
            "added": [_txn("p1_txn1")],
            "modified": [],
            "removed": [],
            "has_more": False,
            "next_cursor": "c1",
        }
    )
    fake_plaid_client.transactions_sync.side_effect = [api_exc, success_page]

    # Don't actually sleep.
    monkeypatch.setattr("core.plaid.sync.time.sleep", lambda _seconds: None)

    sync_transactions(
        client=fake_plaid_client,
        session=session,
        item_id=seeded_chain["item"].item_id,
        access_token="access-sandbox-xyz",
    )

    item = session.scalar(select(Item).where(Item.item_id == seeded_chain["item"].item_id))
    assert item.last_sync_status == "ok"
    assert item.transactions_cursor == "c1"
```

- [ ] **Step 2: Run them — confirm they fail**

```bash
.venv/bin/pytest tests/plaid/test_sync.py -v
```

Expected: the new tests fail with `ImportError` for `sync_transactions`. The 7 tests from Task 6 still pass.

- [ ] **Step 3: Append `sync_transactions` to `core/plaid/sync.py`**

Add the following imports near the top of `core/plaid/sync.py` (after the existing imports):

```python
import json
import time

from plaid.api.plaid_api import PlaidApi
from plaid.exceptions import ApiException
from plaid.model.transactions_sync_request import TransactionsSyncRequest

from core.plaid.errors import classify_plaid_error, is_retryable
```

Then append at the bottom of the file:

```python
_RETRY_DELAYS_SECONDS = [1, 2, 4, 8, 16]  # exponential backoff for retryable errors


def _extract_error_code_and_message(exc: ApiException) -> tuple[str, str]:
    """Pull error_code / error_message out of the JSON body Plaid returns on errors."""
    try:
        body = json.loads(exc.body) if isinstance(exc.body, str) else (exc.body or {})
    except (ValueError, TypeError):
        body = {}
    return body.get("error_code", "UNKNOWN_ERROR"), body.get("error_message", str(exc))


def sync_transactions(
    *,
    client: PlaidApi,
    session: Session,
    item_id: str,
    access_token: str,
) -> None:
    """Drive /transactions/sync to has_more=False, applying each page atomically.

    On retryable Plaid errors (PRODUCT_NOT_READY, RATE_LIMIT_EXCEEDED, INSTITUTION_*),
    backs off exponentially and retries the same page. On non-retryable errors,
    classifies, writes status='error' to the Item, and re-raises.
    """
    item = session.scalar(select(Item).where(Item.item_id == item_id))
    if item is None:
        raise LookupError(f"Item not found: {item_id}")

    cursor = item.transactions_cursor

    while True:
        request = TransactionsSyncRequest(
            access_token=access_token,
            cursor=cursor or "",
        )
        try:
            response = _call_with_retries(client.transactions_sync, request)
        except ApiException as exc:
            code, msg = _extract_error_code_and_message(exc)
            outcome = classify_plaid_error(code, msg)
            item.last_sync_status = outcome.status
            item.last_sync_error = outcome.error
            session.commit()
            raise

        page = response  # has .added, .modified, .removed, .has_more, .next_cursor
        apply_sync_page(session, item_id=item_id, page=page)
        # Each page commits independently — a 500-page Item that fails on page 487
        # keeps pages 1-486 committed and resumes at 487 next run.
        session.commit()

        cursor = page.next_cursor
        if not page.has_more:
            break

    item.last_sync_status = "ok"
    item.last_sync_error = None
    session.commit()


def _call_with_retries(api_call, request) -> Any:
    """Call a Plaid API method with exponential backoff on retryable errors.

    Raises the final ApiException if retries are exhausted, or any non-retryable
    error on first occurrence.
    """
    delays = list(_RETRY_DELAYS_SECONDS)
    while True:
        try:
            return api_call(request)
        except ApiException as exc:
            code, _ = _extract_error_code_and_message(exc)
            if not is_retryable(code) or not delays:
                raise
            time.sleep(delays.pop(0))
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
.venv/bin/pytest tests/plaid/test_sync.py -v
```

Expected: 11 passed (7 from Task 6 + 4 new).

- [ ] **Step 5: Commit**

```bash
git add core/plaid/sync.py tests/plaid/test_sync.py
git commit -m "feat(plaid): sync_transactions multi-page loop + retry/error mapping (Plan 2, Task 7)"
```

---

## Task 8: refresh — balances + holdings

**Files:**
- Create: `core/plaid/refresh.py`
- Create: `tests/plaid/test_refresh.py`

`refresh_balances` calls `/accounts/get` and overwrites the balance columns on every account in the Item. `refresh_holdings` calls `/investments/holdings/get` (only meaningful for Items containing at least one investment account); upserts `securities`, overwrites `holdings`, refreshes investment-account balances.

- [ ] **Step 1: Write the failing test**

Write to `tests/plaid/test_refresh.py`:

```python
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
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
.venv/bin/pytest tests/plaid/test_refresh.py -v
```

Expected: ImportError on `core.plaid.refresh`.

- [ ] **Step 3: Implement `core/plaid/refresh.py`**

Write to `core/plaid/refresh.py`:

```python
"""Balance + holdings refresh.

- refresh_balances: /accounts/get → overwrite Account balance columns.
- refresh_holdings: /investments/holdings/get → upsert Securities, overwrite Holdings,
                    refresh investment Account balances.

Both functions commit the session.
"""
from datetime import date, datetime, timezone
from typing import Any

from plaid.api.plaid_api import PlaidApi
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.investments_holdings_get_request import InvestmentsHoldingsGetRequest
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import Account, Holding, Security


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise TypeError(f"Cannot parse date from {value!r}")


def _apply_account_payload(session: Session, item_id: str, acct_payload: dict, now: datetime) -> None:
    """Upsert one account row from a Plaid account-shaped payload."""
    balances = acct_payload.get("balances") or {}
    existing = session.scalar(
        select(Account).where(Account.account_id == acct_payload["account_id"])
    )
    cols = {
        "name": acct_payload.get("name") or "",
        "official_name": acct_payload.get("official_name"),
        "type": str(acct_payload.get("type")),
        "subtype": str(acct_payload.get("subtype")) if acct_payload.get("subtype") else None,
        "mask": acct_payload.get("mask"),
        "current_balance": balances.get("current"),
        "available_balance": balances.get("available"),
        "limit_balance": balances.get("limit"),
        "iso_currency_code": balances.get("iso_currency_code"),
        "last_balance_at": now,
        "raw_payload": acct_payload,
    }
    if existing is None:
        session.add(
            Account(
                account_id=acct_payload["account_id"],
                item_id=item_id,
                **cols,
            )
        )
    else:
        for k, v in cols.items():
            setattr(existing, k, v)


def has_investment_accounts(session: Session, *, item_id: str) -> bool:
    """True iff this Item has at least one account where type == 'investment'."""
    result = session.scalar(
        select(Account).where(Account.item_id == item_id, Account.type == "investment")
    )
    return result is not None


def refresh_balances(
    *,
    client: PlaidApi,
    session: Session,
    item_id: str,
    access_token: str,
) -> None:
    """Call /accounts/get and overwrite balance columns for every account in this Item."""
    response = client.accounts_get(AccountsGetRequest(access_token=access_token))
    payload = response.to_dict()
    now = _utcnow_naive()
    for acct_payload in payload["accounts"]:
        _apply_account_payload(session, item_id, acct_payload, now)
    session.commit()


def refresh_holdings(
    *,
    client: PlaidApi,
    session: Session,
    item_id: str,
    access_token: str,
) -> None:
    """Call /investments/holdings/get; upsert securities, overwrite holdings, refresh
    investment-account balances. Caller is responsible for only invoking this when
    has_investment_accounts(session, item_id=...) is True."""
    response = client.investments_holdings_get(
        InvestmentsHoldingsGetRequest(access_token=access_token)
    )
    payload = response.to_dict()
    now = _utcnow_naive()

    # 1. Upsert securities.
    for sec_payload in payload.get("securities", []):
        existing = session.scalar(
            select(Security).where(Security.security_id == sec_payload["security_id"])
        )
        cols = {
            "ticker_symbol": sec_payload.get("ticker_symbol"),
            "name": sec_payload.get("name"),
            "type": sec_payload.get("type"),
            "iso_currency_code": sec_payload.get("iso_currency_code"),
            "close_price": sec_payload.get("close_price"),
            "close_price_as_of": _parse_date(sec_payload.get("close_price_as_of")),
        }
        if existing is None:
            session.add(Security(security_id=sec_payload["security_id"], **cols))
        else:
            for k, v in cols.items():
                setattr(existing, k, v)

    # 2. Refresh balances on the accounts in this response (investment accts).
    for acct_payload in payload.get("accounts", []):
        _apply_account_payload(session, item_id, acct_payload, now)

    # 3. Overwrite holdings: delete existing holdings for these accounts, insert fresh.
    affected_account_ids = {h["account_id"] for h in payload.get("holdings", [])}
    if affected_account_ids:
        existing_holdings = session.scalars(
            select(Holding).where(Holding.account_id.in_(affected_account_ids))
        ).all()
        for h in existing_holdings:
            session.delete(h)
        session.flush()

    for h_payload in payload.get("holdings", []):
        session.add(
            Holding(
                account_id=h_payload["account_id"],
                security_id=h_payload["security_id"],
                quantity=float(h_payload.get("quantity", 0.0)),
                institution_price=h_payload.get("institution_price"),
                institution_value=h_payload.get("institution_value"),
                cost_basis=h_payload.get("cost_basis"),
                last_synced_at=now,
            )
        )

    session.commit()
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/plaid/test_refresh.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add core/plaid/refresh.py tests/plaid/test_refresh.py
git commit -m "feat(plaid): refresh_balances + refresh_holdings (Plan 2, Task 8)"
```

---

## Task 9: Sync orchestrator — per-Item lock + ThreadPoolExecutor

**Files:**
- Create: `core/plaid/orchestrator.py`
- Create: `tests/plaid/test_orchestrator.py`

The orchestrator wraps Tasks 5-8 into one callable per Item: `sync_item(item_id)` does decrypt → sync_transactions → refresh_balances → (if investment) refresh_holdings, all guarded by a per-Item lock so manual sync can't race the auto-sync. `sync_all_items()` parallelizes across Items via a ThreadPoolExecutor.

- [ ] **Step 1: Write the failing test**

Write to `tests/plaid/test_orchestrator.py`:

```python
import threading
from unittest.mock import MagicMock, call

import pytest
from sqlalchemy import select

from core.db import Account, Item, make_session_factory
from core.plaid.orchestrator import (
    PerItemLockRegistry,
    sync_all_items,
    sync_item,
)


def _make_session_factory(engine):
    return make_session_factory(engine)


def test_per_item_lock_registry_returns_same_lock_per_item_id():
    reg = PerItemLockRegistry()
    a1 = reg.lock_for("item_A")
    a2 = reg.lock_for("item_A")
    b = reg.lock_for("item_B")
    assert a1 is a2
    assert a1 is not b


def test_sync_item_marks_status_ok_on_success(
    engine, seeded_chain, fake_plaid_client, make_response, fake_keychain, monkeypatch
):
    """sync_item runs sync_transactions + refresh_balances; status='ok' afterwards."""
    # First, store a real ciphertext on the Item so decrypt works.
    SessionLocal = _make_session_factory(engine)
    with SessionLocal() as s:
        from core.plaid.tokens import store_encrypted_token
        store_encrypted_token(s, item_id="item_test", access_token="access-sandbox-xyz")
        s.commit()

    # transactions_sync: one empty page, has_more=False.
    fake_plaid_client.transactions_sync.return_value = make_response(
        {
            "added": [],
            "modified": [],
            "removed": [],
            "has_more": False,
            "next_cursor": "c_done",
        }
    )
    # accounts_get: refresh balance.
    fake_plaid_client.accounts_get.return_value = make_response(
        {
            "item": {"item_id": "item_test", "institution_id": "ins_test"},
            "accounts": [
                {
                    "account_id": "acc_test",
                    "name": "Checking",
                    "official_name": None,
                    "type": "depository",
                    "subtype": "checking",
                    "mask": "0000",
                    "balances": {
                        "current": 1234.56,
                        "available": 1234.56,
                        "limit": None,
                        "iso_currency_code": "USD",
                    },
                }
            ],
        }
    )

    sync_item(
        client_factory=lambda: fake_plaid_client,
        session_factory=SessionLocal,
        item_id="item_test",
    )

    with SessionLocal() as s:
        item = s.scalar(select(Item).where(Item.item_id == "item_test"))
        assert item.last_sync_status == "ok"
        assert item.transactions_cursor == "c_done"
        acct = s.scalar(select(Account).where(Account.account_id == "acc_test"))
        assert acct.current_balance == 1234.56

    # Investment-only call should NOT have happened (no investment account).
    fake_plaid_client.investments_holdings_get.assert_not_called()


def test_sync_item_skips_holdings_when_no_investment_account(
    engine, seeded_chain, fake_plaid_client, make_response, fake_keychain
):
    """has_investment_accounts is False → investments_holdings_get NOT called."""
    SessionLocal = _make_session_factory(engine)
    with SessionLocal() as s:
        from core.plaid.tokens import store_encrypted_token
        store_encrypted_token(s, item_id="item_test", access_token="access-sandbox-xyz")
        s.commit()

    fake_plaid_client.transactions_sync.return_value = make_response(
        {"added": [], "modified": [], "removed": [], "has_more": False, "next_cursor": "c"}
    )
    fake_plaid_client.accounts_get.return_value = make_response(
        {
            "item": {"item_id": "item_test", "institution_id": "ins_test"},
            "accounts": [],
        }
    )

    sync_item(
        client_factory=lambda: fake_plaid_client,
        session_factory=SessionLocal,
        item_id="item_test",
    )

    fake_plaid_client.investments_holdings_get.assert_not_called()


def test_sync_all_items_runs_each_in_parallel_isolated(
    engine, fake_keychain
):
    """Two Items, two fake clients — both run, both report ok, neither blocks the other."""
    SessionLocal = _make_session_factory(engine)
    # Seed two items + accounts + ciphertexts.
    with SessionLocal() as s:
        from core.db import Account, Institution, Item
        from core.plaid.tokens import store_encrypted_token
        s.add(Institution(institution_id="ins_X", name="X Bank"))
        for iid in ("item_X1", "item_X2"):
            s.add(Item(item_id=iid, institution_id="ins_X", access_token_ciphertext=b"\x00" * 28))
        s.add(Account(account_id="acc_X1", item_id="item_X1", name="A", type="depository"))
        s.add(Account(account_id="acc_X2", item_id="item_X2", name="B", type="depository"))
        s.flush()
        store_encrypted_token(s, item_id="item_X1", access_token="t1")
        store_encrypted_token(s, item_id="item_X2", access_token="t2")
        s.commit()

    def client_factory():
        c = MagicMock()
        c.transactions_sync.return_value = MagicMock(
            added=[],
            modified=[],
            removed=[],
            has_more=False,
            next_cursor="c",
            to_dict=lambda: {
                "added": [], "modified": [], "removed": [], "has_more": False, "next_cursor": "c",
            },
        )
        c.accounts_get.return_value = MagicMock(
            to_dict=lambda: {
                "item": {"item_id": "?", "institution_id": "ins_X"},
                "accounts": [],
            }
        )
        return c

    sync_all_items(
        client_factory=client_factory,
        session_factory=SessionLocal,
        item_ids=["item_X1", "item_X2"],
    )

    with SessionLocal() as s:
        items = s.scalars(select(Item).where(Item.item_id.in_(["item_X1", "item_X2"]))).all()
        assert all(i.last_sync_status == "ok" for i in items)


def test_sync_all_items_one_failure_does_not_block_others(
    engine, fake_keychain
):
    """One Item raises; the other still completes successfully."""
    SessionLocal = _make_session_factory(engine)
    with SessionLocal() as s:
        from core.db import Account, Institution, Item
        from core.plaid.tokens import store_encrypted_token
        s.add(Institution(institution_id="ins_X", name="X Bank"))
        s.add(Item(item_id="item_good", institution_id="ins_X", access_token_ciphertext=b"\x00" * 28))
        s.add(Item(item_id="item_bad", institution_id="ins_X", access_token_ciphertext=b"\x00" * 28))
        s.add(Account(account_id="acc_good", item_id="item_good", name="A", type="depository"))
        s.add(Account(account_id="acc_bad", item_id="item_bad", name="B", type="depository"))
        s.flush()
        store_encrypted_token(s, item_id="item_good", access_token="t_good")
        store_encrypted_token(s, item_id="item_bad", access_token="t_bad")
        s.commit()

    def client_factory():
        c = MagicMock()
        # Different per-call behavior depending on access_token in the request.
        def transactions_sync_side_effect(req):
            if req.access_token == "t_bad":
                raise RuntimeError("simulated network error")
            response = MagicMock()
            response.added = []
            response.modified = []
            response.removed = []
            response.has_more = False
            response.next_cursor = "c"
            return response

        c.transactions_sync.side_effect = transactions_sync_side_effect
        c.accounts_get.return_value = MagicMock(
            to_dict=lambda: {"item": {"item_id": "?", "institution_id": "ins_X"}, "accounts": []}
        )
        return c

    sync_all_items(
        client_factory=client_factory,
        session_factory=SessionLocal,
        item_ids=["item_good", "item_bad"],
    )

    with SessionLocal() as s:
        good = s.scalar(select(Item).where(Item.item_id == "item_good"))
        bad = s.scalar(select(Item).where(Item.item_id == "item_bad"))
        assert good.last_sync_status == "ok"
        assert bad.last_sync_status == "error"


def test_per_item_lock_serializes_overlapping_calls(
    engine, seeded_chain, fake_plaid_client, make_response, fake_keychain
):
    """Two threads calling sync_item for the same item_id — the second waits.

    Detected by counting transactions_sync calls and asserting they don't overlap.
    """
    SessionLocal = _make_session_factory(engine)
    with SessionLocal() as s:
        from core.plaid.tokens import store_encrypted_token
        store_encrypted_token(s, item_id="item_test", access_token="access-sandbox-xyz")
        s.commit()

    in_flight = threading.Event()
    can_finish = threading.Event()
    overlap_detected = []

    def slow_sync(req):
        # If we see this called while another call is in flight, that's an overlap.
        if in_flight.is_set():
            overlap_detected.append(True)
        in_flight.set()
        can_finish.wait(timeout=2)  # block until released
        in_flight.clear()
        response = MagicMock()
        response.added, response.modified, response.removed = [], [], []
        response.has_more = False
        response.next_cursor = "c"
        return response

    fake_plaid_client.transactions_sync.side_effect = slow_sync
    fake_plaid_client.accounts_get.return_value = make_response(
        {"item": {"item_id": "item_test", "institution_id": "ins_test"}, "accounts": []}
    )

    registry = PerItemLockRegistry()

    def call_sync():
        sync_item(
            client_factory=lambda: fake_plaid_client,
            session_factory=SessionLocal,
            item_id="item_test",
            lock_registry=registry,
        )

    t1 = threading.Thread(target=call_sync)
    t2 = threading.Thread(target=call_sync)
    t1.start()
    # Give t1 time to acquire the lock and start the slow_sync.
    in_flight.wait(timeout=1)
    t2.start()
    can_finish.set()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert overlap_detected == []  # the lock prevented overlap
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
.venv/bin/pytest tests/plaid/test_orchestrator.py -v
```

Expected: ImportError on `core.plaid.orchestrator`.

- [ ] **Step 3: Implement `core/plaid/orchestrator.py`**

Write to `core/plaid/orchestrator.py`:

```python
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
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
.venv/bin/pytest tests/plaid/test_orchestrator.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add core/plaid/orchestrator.py tests/plaid/test_orchestrator.py
git commit -m "feat(plaid): orchestrator with per-Item lock + thread-pool fanout (Plan 2, Task 9)"
```

---

## Task 10: Plaid package public API

**Files:**
- Modify: `core/plaid/__init__.py`

- [ ] **Step 1: Replace `core/plaid/__init__.py` content**

Write to `core/plaid/__init__.py`:

```python
"""Plaid integration — client, link, sync, refresh, orchestrator.

Public API:
- PlaidEnv, make_plaid_client
- create_link_token, exchange_public_token
- sync_transactions, apply_sync_page
- refresh_balances, refresh_holdings, has_investment_accounts
- sync_item, sync_all_items, PerItemLockRegistry
- store_encrypted_token, load_decrypted_token
- classify_plaid_error, is_retryable, SyncOutcome
"""
from core.plaid.client import PlaidEnv, make_plaid_client
from core.plaid.errors import SyncOutcome, classify_plaid_error, is_retryable
from core.plaid.link import create_link_token, exchange_public_token
from core.plaid.orchestrator import (
    PerItemLockRegistry,
    sync_all_items,
    sync_item,
)
from core.plaid.refresh import (
    has_investment_accounts,
    refresh_balances,
    refresh_holdings,
)
from core.plaid.sync import apply_sync_page, sync_transactions
from core.plaid.tokens import load_decrypted_token, store_encrypted_token

__all__ = [
    "PerItemLockRegistry",
    "PlaidEnv",
    "SyncOutcome",
    "apply_sync_page",
    "classify_plaid_error",
    "create_link_token",
    "exchange_public_token",
    "has_investment_accounts",
    "is_retryable",
    "load_decrypted_token",
    "make_plaid_client",
    "refresh_balances",
    "refresh_holdings",
    "store_encrypted_token",
    "sync_all_items",
    "sync_item",
    "sync_transactions",
]
```

- [ ] **Step 2: Run the full suite**

```bash
.venv/bin/pytest -v
```

Expected: all tests pass (28 from Plan 1 + new tests from Plan 2 Tasks 2-9).

- [ ] **Step 3: Commit**

```bash
git add core/plaid/__init__.py
git commit -m "feat(plaid): package public API exports (Plan 2, Task 10)"
```

---

## Task 11: Plaid Sandbox integration ring (optional, marked, skipped by default)

**Files:**
- Create: `tests/plaid/test_sandbox_integration.py`

This test ring runs against Plaid Sandbox (free, deterministic credentials `user_good`/`pass_good`). It is the *only* test that hits real Plaid network endpoints. Marked `@pytest.mark.sandbox` and skipped unless explicitly requested.

- [ ] **Step 1: Write the integration test**

Write to `tests/plaid/test_sandbox_integration.py`:

```python
"""Plaid Sandbox integration ring — runs only with `pytest -m sandbox`.

Requires PLAID_CLIENT_ID and PLAID_SECRET in env (Plaid Sandbox credentials).
Free; deterministic data. Run with:

    PLAID_CLIENT_ID=<sandbox cid> PLAID_SECRET=<sandbox secret> \
      .venv/bin/pytest -m sandbox -v
"""
import os

import pytest
from plaid.model.country_code import CountryCode
from plaid.model.products import Products
from plaid.model.sandbox_public_token_create_request import (
    SandboxPublicTokenCreateRequest,
)
from sqlalchemy import select

from core.db import Item, Transaction, make_session_factory
from core.plaid import (
    PlaidEnv,
    exchange_public_token,
    make_plaid_client,
    sync_item,
)


# Skip the entire module unless PLAID_CLIENT_ID/SECRET are set.
pytestmark = [
    pytest.mark.sandbox,
    pytest.mark.skipif(
        not (os.environ.get("PLAID_CLIENT_ID") and os.environ.get("PLAID_SECRET")),
        reason="PLAID_CLIENT_ID and PLAID_SECRET must be set",
    ),
]


@pytest.fixture
def sandbox_client():
    return make_plaid_client(
        env=PlaidEnv.SANDBOX,
        client_id=os.environ["PLAID_CLIENT_ID"],
        secret=os.environ["PLAID_SECRET"],
    )


def _create_sandbox_public_token(client) -> str:
    """Use Plaid's sandbox-only endpoint to mint a public_token without UI."""
    resp = client.sandbox_public_token_create(
        SandboxPublicTokenCreateRequest(
            institution_id="ins_109508",  # Plaid's "First Platypus Bank" — always available
            initial_products=[Products("transactions")],
        )
    )
    return resp.public_token


def test_full_link_then_sync_against_sandbox(engine, fake_keychain, sandbox_client):
    """End-to-end: mint a sandbox public_token → exchange → sync_item → assert rows landed."""
    SessionLocal = make_session_factory(engine)

    public_token = _create_sandbox_public_token(sandbox_client)
    with SessionLocal() as s:
        item_id = exchange_public_token(
            client=sandbox_client, session=s, public_token=public_token
        )

    sync_item(
        client_factory=lambda: sandbox_client,
        session_factory=SessionLocal,
        item_id=item_id,
    )

    with SessionLocal() as s:
        item = s.scalar(select(Item).where(Item.item_id == item_id))
        assert item.last_sync_status == "ok", (item.last_sync_status, item.last_sync_error)
        # Sandbox accounts always have at least a few transactions.
        txns = s.scalars(select(Transaction)).all()
        assert len(txns) > 0
```

- [ ] **Step 2: Confirm it's skipped by default**

```bash
.venv/bin/pytest tests/plaid/test_sandbox_integration.py -v
```

Expected: the test is skipped (because `PLAID_CLIENT_ID`/`PLAID_SECRET` are not set in your env unless you explicitly set them). Output should show `1 skipped`.

- [ ] **Step 3: Run the full suite — confirm sandbox tests don't slow it down**

```bash
.venv/bin/pytest -v
```

Expected: all unit tests pass; sandbox test is skipped. Total time should be similar to the previous run.

- [ ] **Step 4: (Optional, user-driven) Run the sandbox test for real**

Get sandbox credentials from your Plaid dashboard (`dashboard.plaid.com` → Team Settings → Keys → Sandbox), then:

```bash
PLAID_CLIENT_ID=<your sandbox client_id> \
PLAID_SECRET=<your sandbox secret> \
.venv/bin/pytest -m sandbox -v
```

Expected: `1 passed` (~3-5 seconds, includes one real network round-trip per Plaid call).

If this fails: the most common cause is a plaid-python version drift in the `Sandbox*` model classes. Check the import in `tests/plaid/test_sandbox_integration.py` against `pip show -f plaid-python | grep -i sandbox`. Fix the import; the test logic is stable.

- [ ] **Step 5: Commit**

```bash
git add tests/plaid/test_sandbox_integration.py
git commit -m "feat(plaid): sandbox integration ring (Plan 2, Task 11)"
```

---

## Plan 2 Verification

```bash
.venv/bin/pytest --cov=core --cov-report=term-missing -v
```

Expected:
- All unit tests pass; sandbox test skipped.
- New test counts (rough): Task 2: 3, Task 3: 5, Task 4: 6, Task 5: 3, Task 6: 7, Task 7: 4, Task 8: 5, Task 9: 5 = ~38 new tests on top of Plan 1's 28 = ~66 total.
- Coverage target: 90%+ on `core/plaid/*` (sandbox-only paths may dip slightly).

```bash
git log --oneline | head -15
```

Expected: 11 new commits on top of Plan 1's 8 = 19 total commits, with Plan 2 commits prefixed `chore:` (Task 1 polish) and `feat(plaid):` (Tasks 2-11).

---

## Hand-off to Plan 3

Plan 3 (Read layer) will add `core/queries/`:
- `core/queries/transactions.py` — `search_transactions(filters)`.
- `core/queries/networth.py` — `net_worth(at_date=None)`.
- `core/queries/categories.py` — `category_spend(start, end)`.
- `core/queries/holdings.py` — `list_holdings()`.
- `core/queries/accounts.py` — `list_accounts()`.
- All pure read, no Plaid calls — both api/ (Plan 4) and mcp/ (Plan 6) consume these.
- Tests with seeded fixtures (the shared `seeded_chain` from this plan's `tests/conftest.py` will be reused and extended).
