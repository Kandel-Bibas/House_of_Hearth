# Plan 4 — API + Launcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** Add the FastAPI HTTP layer (`api/` package), wire it to all the existing `core/*` modules, add a `make dev` script and a desktop `.command` launcher. After this plan, the user can double-click an icon, browse to `localhost:8000/docs`, and exercise every flow via curl/JSON. The frontend (Plan 5) will add the UI.

**Architecture:** FastAPI app with thin routers. Each route is a 3–5 line wrapper around `core/*`. Sync runs as a `BackgroundTasks` task. Pydantic v2 response models for JSON shape. CORS enabled for `localhost:5173` (Vite dev server, Plan 5). Single `uvicorn api.main:app` invocation; no async DB.

**Tech Stack:** FastAPI, Pydantic v2, uvicorn (already a transitive dep, will add explicitly), `python-multipart` (FastAPI form parsing).

**Spec reference:** `docs/superpowers/specs/2026-04-26-finance-tracker-design.md` — section 4.2 (boot sequence), section 5.* (HTTP routes), section 7.4 (concurrency).

---

## File Structure

```
api/
├── __init__.py
├── main.py             # FastAPI app, startup/shutdown hooks, CORS, router mounting
├── deps.py             # Session dependency, Plaid client dependency
├── routes/
│   ├── __init__.py
│   ├── plaid.py        # POST /plaid/link-token, POST /plaid/exchange
│   ├── sync.py         # POST /sync, GET /sync/status
│   ├── accounts.py     # GET /accounts
│   ├── transactions.py # GET /transactions
│   ├── holdings.py     # GET /holdings
│   ├── networth.py     # GET /networth
│   └── categories.py   # GET /category-spend
└── schemas.py          # Pydantic v2 response models

scripts/
├── make-dev            # Helper invoked by Makefile (just runs uvicorn for now;
│                       # Plan 5 will extend to also run Vite)
└── finance-tracker.command  # macOS double-clickable launcher
                        # → opens Terminal, runs `cd <project> && make dev`

Makefile                # `make dev`, `make test`, `make migrate`

tests/api/
├── __init__.py
├── conftest.py         # TestClient + override session dep
├── test_plaid_routes.py
├── test_sync_routes.py
├── test_read_routes.py
└── test_startup.py
```

---

## Task 1: FastAPI scaffold + dependencies

**Files:**
- Modify: `pyproject.toml` (add `fastapi`, `uvicorn[standard]`, `python-multipart`)
- Create: `api/__init__.py`, `api/main.py`, `api/deps.py`, `api/schemas.py`
- Create: `api/routes/__init__.py`
- Create: `tests/api/__init__.py`, `tests/api/conftest.py`

- [ ] **Step 1: Add deps to `pyproject.toml`**

In `pyproject.toml`, change `dependencies` to add three FastAPI packages:

```toml
dependencies = [
    "sqlalchemy>=2.0,<3",
    "alembic>=1.13,<2",
    "cryptography>=42.0",
    "keyring>=25.0",
    "plaid-python>=24.0,<32",
    "fastapi>=0.115,<1",
    "uvicorn[standard]>=0.32,<1",
    "python-multipart>=0.0.18",
]
```

Add `httpx>=0.27` to dev deps for FastAPI's TestClient:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
    "httpx>=0.27",
]
```

- [ ] **Step 2: Reinstall**

```bash
cd /path/to/house_of_hearth
.venv/bin/pip install -e ".[dev]"
```

- [ ] **Step 3: Create skeleton files**

```bash
mkdir -p api/routes tests/api
touch api/__init__.py api/routes/__init__.py tests/api/__init__.py
```

- [ ] **Step 4: Write `api/deps.py`**

```python
"""FastAPI dependency providers — session, Plaid client.

`get_session` yields a SQLAlchemy session bound to the app's engine.
`get_plaid_client` builds a PlaidApi from environment variables.

Both are overridable in tests via app.dependency_overrides.
"""
import os
from typing import Generator

from fastapi import Depends
from plaid.api.plaid_api import PlaidApi
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from core.db import DEFAULT_DATABASE_URL, make_engine, make_session_factory
from core.plaid import PlaidEnv, make_plaid_client


_engine: Engine | None = None
_SessionLocal = None


def _ensure_engine() -> None:
    global _engine, _SessionLocal
    if _engine is None:
        url = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
        _engine = make_engine(url)
        _SessionLocal = make_session_factory(_engine)


def get_session() -> Generator[Session, None, None]:
    _ensure_engine()
    assert _SessionLocal is not None
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_plaid_client() -> PlaidApi:
    env_str = os.environ.get("PLAID_ENV", "sandbox").lower()
    env = PlaidEnv(env_str)
    client_id = os.environ.get("PLAID_CLIENT_ID", "")
    secret = os.environ.get("PLAID_SECRET", "")
    return make_plaid_client(env=env, client_id=client_id, secret=secret)


def get_engine() -> Engine:
    """Used by the startup hook (Alembic, sync orchestrator). Not a route dep."""
    _ensure_engine()
    assert _engine is not None
    return _engine


def get_session_factory():
    """Used by the orchestrator (one session per worker thread)."""
    _ensure_engine()
    assert _SessionLocal is not None
    return _SessionLocal
```

- [ ] **Step 5: Write `api/schemas.py`**

```python
"""Pydantic v2 response models — keep API JSON shape stable across refactors.

Only the response models are explicit; request bodies are minimal and inline in routes.
"""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=False)

    account_id: str
    name: str
    official_name: Optional[str] = None
    type: str
    subtype: Optional[str] = None
    mask: Optional[str] = None
    current_balance: Optional[float] = None
    available_balance: Optional[float] = None
    limit_balance: Optional[float] = None
    iso_currency_code: Optional[str] = None
    last_balance_at: Optional[str] = None
    item_id: str
    institution_id: str
    institution_name: str
    institution_logo: Optional[str] = None
    institution_primary_color: Optional[str] = None
    last_sync_status: Optional[str] = None
    last_sync_error: Optional[str] = None
    last_sync_at: Optional[str] = None


class TransactionOut(BaseModel):
    transaction_id: str
    account_id: str
    date: Optional[str] = None
    authorized_date: Optional[str] = None
    amount: float
    iso_currency_code: Optional[str] = None
    name: str
    merchant_name: Optional[str] = None
    payment_channel: Optional[str] = None
    pending: bool
    category_primary: Optional[str] = None
    category_detailed: Optional[str] = None
    category_confidence: Optional[str] = None
    removed_at: Optional[str] = None


class HoldingOut(BaseModel):
    account_id: str
    account_name: str
    security_id: str
    ticker_symbol: Optional[str] = None
    security_name: Optional[str] = None
    security_type: Optional[str] = None
    quantity: float
    institution_price: Optional[float] = None
    institution_value: Optional[float] = None
    cost_basis: Optional[float] = None
    iso_currency_code: Optional[str] = None


class NetWorthOut(BaseModel):
    total: float
    depository: float
    credit: float
    investment: float
    loan: float


class CategorySpendRow(BaseModel):
    category_primary: str
    total: float
    count: int


class LinkTokenOut(BaseModel):
    link_token: str


class ExchangeIn(BaseModel):
    public_token: str


class ExchangeOut(BaseModel):
    item_id: str


class SyncStartedOut(BaseModel):
    started: bool
    item_count: int


class SyncStatusOut(BaseModel):
    item_id: str
    institution_name: str
    last_sync_status: Optional[str] = None
    last_sync_error: Optional[str] = None
    last_sync_at: Optional[str] = None
```

- [ ] **Step 6: Write minimal `api/main.py`**

```python
"""FastAPI app entry point.

Run with: `uvicorn api.main:app --reload --port 8000`

The startup hook is added in Task 4. For now, this is a bare app + CORS
so route tests can run.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


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

    # Routers are mounted in subsequent tasks.
    return app


app = create_app()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 7: Write `tests/api/conftest.py`**

```python
"""TestClient that overrides the session dependency to use a per-test in-memory DB."""
import pytest
from fastapi.testclient import TestClient

from api.deps import get_session, get_plaid_client
from api.main import app
from core.db import Base, make_session_factory


@pytest.fixture
def client(engine):
    """A FastAPI TestClient with get_session bound to the per-test engine."""
    Base.metadata.create_all(engine)
    SessionLocal = make_session_factory(engine)

    def _override_session():
        s = SessionLocal()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_session] = _override_session

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture
def client_with_plaid(client, fake_plaid_client):
    """As `client`, but get_plaid_client also overridden to the MagicMock."""
    app.dependency_overrides[get_plaid_client] = lambda: fake_plaid_client
    yield client
    # cleanup happens in the `client` fixture's teardown
```

Note: this conftest depends on the `engine` fixture from `tests/conftest.py` (the shared one) and `fake_plaid_client` from `tests/plaid/conftest.py`. Since pytest discovers conftests up the tree, `tests/api/conftest.py` automatically inherits both. We re-import `fake_plaid_client` here only as a name; the actual fixture resolution comes from `tests/plaid/conftest.py`.

Hmm wait — `fake_plaid_client` is in `tests/plaid/conftest.py`, but `tests/api/` is a sibling. Pytest fixture lookup walks UP the directory tree, not sideways. So `tests/api/test_*.py` does NOT see `fake_plaid_client` from `tests/plaid/conftest.py`.

**Fix:** move the `fake_plaid_client` and `make_response` fixtures from `tests/plaid/conftest.py` to `tests/conftest.py` (the shared one) so both `tests/plaid/` and `tests/api/` see them.

- [ ] **Step 8: Hoist `fake_plaid_client` + `make_response` to `tests/conftest.py`**

Open `tests/conftest.py` and append (after the existing fixtures):

```python
# ----- Plaid client mocks (shared across tests/plaid/ and tests/api/) -----------
from unittest.mock import MagicMock as _MagicMock


@pytest.fixture
def fake_plaid_client():
    """A MagicMock standing in for plaid.api.plaid_api.PlaidApi."""
    return _MagicMock(name="fake_plaid_client")


def _wrap(payload: dict):
    obj = _MagicMock()
    obj.to_dict.return_value = payload
    for key, value in payload.items():
        setattr(obj, key, value)
    return obj


@pytest.fixture
def make_response():
    """Wrap a dict so `.to_dict()` and attribute access both work."""
    return _wrap
```

Then **delete** the duplicate fixtures from `tests/plaid/conftest.py`. Replace its content with:

```python
"""Plaid-specific test helpers.

The `fake_plaid_client` and `make_response` fixtures are defined in `tests/conftest.py`
so they're available to both `tests/plaid/` and `tests/api/`. This file is kept as a
placeholder for future plaid-specific fixtures.
"""
```

- [ ] **Step 9: Run the suite — confirm no regression**

```bash
.venv/bin/pytest -v
```

Expected: 93 passed + 1 skipped (no tests added in this task; just fixture reorg).

If a test in `tests/plaid/` fails because `fake_plaid_client`/`make_response` are no longer in scope, double-check the hoist worked. Pytest discovers `tests/conftest.py` for everything under `tests/`.

- [ ] **Step 10: Commit**

```bash
git add pyproject.toml api tests/api tests/conftest.py tests/plaid/conftest.py
git commit -m "feat(api): scaffold FastAPI app + deps + schemas + test client (Plan 4, Task 1)"
```

---

## Task 2: Plaid routes (link-token, exchange)

**Files:**
- Create: `api/routes/plaid.py`
- Modify: `api/main.py` (mount the router)
- Create: `tests/api/test_plaid_routes.py`

- [ ] **Step 1: Write the failing test**

Write to `tests/api/test_plaid_routes.py`:

```python
from sqlalchemy import select

from core.db import Item
from core.plaid.tokens import load_decrypted_token


def test_link_token_route(client_with_plaid, fake_plaid_client, make_response):
    fake_plaid_client.link_token_create.return_value = make_response(
        {"link_token": "link-sandbox-XYZ", "expiration": "2026-04-27T00:00:00Z"}
    )
    resp = client_with_plaid.post("/plaid/link-token")
    assert resp.status_code == 200
    assert resp.json() == {"link_token": "link-sandbox-XYZ"}


def test_exchange_route(
    client_with_plaid, fake_plaid_client, make_response, fake_keychain
):
    fake_plaid_client.item_public_token_exchange.return_value = make_response(
        {"access_token": "access-sandbox-XYZ", "item_id": "item_NEW"}
    )
    fake_plaid_client.accounts_get.return_value = make_response(
        {
            "item": {"item_id": "item_NEW", "institution_id": "ins_test"},
            "accounts": [
                {
                    "account_id": "acc_NEW",
                    "name": "Plaid Checking",
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
    fake_plaid_client.institutions_get_by_id.return_value = make_response(
        {
            "institution": {
                "institution_id": "ins_test",
                "name": "Test Bank",
                "primary_color": "#000",
                "url": "https://test.example",
                "logo": None,
            }
        }
    )

    resp = client_with_plaid.post(
        "/plaid/exchange", json={"public_token": "public-sandbox-PUB"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"item_id": "item_NEW"}


def test_exchange_with_missing_public_token_returns_422(client_with_plaid):
    resp = client_with_plaid.post("/plaid/exchange", json={})
    assert resp.status_code == 422
```

- [ ] **Step 2: Run — confirm failure**

```bash
.venv/bin/pytest tests/api/test_plaid_routes.py -v
```

Expected: 404 (router not mounted yet) or import error.

- [ ] **Step 3: Write `api/routes/plaid.py`**

```python
"""Plaid Link routes."""
from fastapi import APIRouter, Depends
from plaid.api.plaid_api import PlaidApi
from sqlalchemy.orm import Session

from api.deps import get_plaid_client, get_session
from api.schemas import ExchangeIn, ExchangeOut, LinkTokenOut
from core.plaid.link import create_link_token, exchange_public_token

router = APIRouter(prefix="/plaid", tags=["plaid"])


@router.post("/link-token", response_model=LinkTokenOut)
def link_token_route(
    client: PlaidApi = Depends(get_plaid_client),
) -> LinkTokenOut:
    token = create_link_token(client=client, client_user_id="local-user")
    return LinkTokenOut(link_token=token)


@router.post("/exchange", response_model=ExchangeOut)
def exchange_route(
    body: ExchangeIn,
    session: Session = Depends(get_session),
    client: PlaidApi = Depends(get_plaid_client),
) -> ExchangeOut:
    item_id = exchange_public_token(
        client=client, session=session, public_token=body.public_token
    )
    return ExchangeOut(item_id=item_id)
```

- [ ] **Step 4: Mount the router in `api/main.py`**

Add to `api/main.py` inside `create_app()` (before `return app`):

```python
    from api.routes import plaid as plaid_routes
    app.include_router(plaid_routes.router)
```

- [ ] **Step 5: Run tests**

```bash
.venv/bin/pytest tests/api/test_plaid_routes.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add api/routes/plaid.py api/main.py tests/api/test_plaid_routes.py
git commit -m "feat(api): /plaid/link-token + /plaid/exchange routes (Plan 4, Task 2)"
```

---

## Task 3: Read routes (accounts, transactions, holdings, networth, categories)

**Files:**
- Create: `api/routes/{accounts,transactions,holdings,networth,categories}.py`
- Modify: `api/main.py` (mount 5 more routers)
- Create: `tests/api/test_read_routes.py`

- [ ] **Step 1: Write the failing test**

Write to `tests/api/test_read_routes.py`:

```python
from datetime import date


def test_accounts_route_returns_list(client, queries_seed):
    resp = client.get("/accounts")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 3
    by_id = {a["account_id"]: a for a in body}
    assert by_id["acc_test"]["name"] == "Checking"
    assert by_id["acc_credit"]["type"] == "credit"


def test_transactions_route_default(client, queries_seed):
    resp = client.get("/transactions")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 5  # 5 non-removed
    assert body[0]["date"] >= body[-1]["date"]


def test_transactions_route_filters(client, queries_seed):
    resp = client.get(
        "/transactions",
        params={"start_date": "2026-04-01", "end_date": "2026-04-03",
                "category_primary": "FOOD_AND_DRINK", "min_amount": "40.0"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert {t["transaction_id"] for t in body} == {"txn_grocery_1"}


def test_holdings_route(client, queries_seed):
    resp = client.get("/holdings")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["ticker_symbol"] == "VTI"


def test_networth_route(client, queries_seed):
    resp = client.get("/networth")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 11250.00
    assert body["depository"] == 1000.00
    assert body["investment"] == 10000.00


def test_category_spend_route(client, queries_seed):
    resp = client.get(
        "/category-spend",
        params={"start_date": "2026-04-01", "end_date": "2026-04-30"},
    )
    assert resp.status_code == 200
    body = resp.json()
    by_cat = {row["category_primary"]: row for row in body}
    assert by_cat["FOOD_AND_DRINK"]["total"] == 164.75
    assert by_cat["FOOD_AND_DRINK"]["count"] == 3
```

- [ ] **Step 2: Run — confirm failure (404s)**

```bash
.venv/bin/pytest tests/api/test_read_routes.py -v
```

Expected: 6 failures.

- [ ] **Step 3: Write `api/routes/accounts.py`**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.deps import get_session
from api.schemas import AccountOut
from core.queries import list_accounts

router = APIRouter(tags=["accounts"])


@router.get("/accounts", response_model=list[AccountOut])
def accounts_route(session: Session = Depends(get_session)) -> list[AccountOut]:
    return [AccountOut(**row) for row in list_accounts(session)]
```

- [ ] **Step 4: Write `api/routes/transactions.py`**

```python
from datetime import date as date_t
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.deps import get_session
from api.schemas import TransactionOut
from core.queries import search_transactions

router = APIRouter(tags=["transactions"])


@router.get("/transactions", response_model=list[TransactionOut])
def transactions_route(
    session: Session = Depends(get_session),
    start_date: Optional[date_t] = Query(None),
    end_date: Optional[date_t] = Query(None),
    account_id: Optional[str] = Query(None),
    category_primary: Optional[str] = Query(None),
    category_detailed: Optional[str] = Query(None),
    merchant_name: Optional[str] = Query(None),
    min_amount: Optional[float] = Query(None),
    max_amount: Optional[float] = Query(None),
    include_removed: bool = Query(False),
    limit: Optional[int] = Query(None, ge=1, le=10000),
) -> list[TransactionOut]:
    rows = search_transactions(
        session,
        start_date=start_date,
        end_date=end_date,
        account_id=account_id,
        category_primary=category_primary,
        category_detailed=category_detailed,
        merchant_name=merchant_name,
        min_amount=min_amount,
        max_amount=max_amount,
        include_removed=include_removed,
        limit=limit,
    )
    return [TransactionOut(**row) for row in rows]
```

- [ ] **Step 5: Write `api/routes/holdings.py`**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.deps import get_session
from api.schemas import HoldingOut
from core.queries import list_holdings

router = APIRouter(tags=["holdings"])


@router.get("/holdings", response_model=list[HoldingOut])
def holdings_route(session: Session = Depends(get_session)) -> list[HoldingOut]:
    return [HoldingOut(**row) for row in list_holdings(session)]
```

- [ ] **Step 6: Write `api/routes/networth.py`**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.deps import get_session
from api.schemas import NetWorthOut
from core.queries import net_worth

router = APIRouter(tags=["networth"])


@router.get("/networth", response_model=NetWorthOut)
def networth_route(session: Session = Depends(get_session)) -> NetWorthOut:
    return NetWorthOut(**net_worth(session))
```

- [ ] **Step 7: Write `api/routes/categories.py`**

```python
from datetime import date as date_t

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.deps import get_session
from api.schemas import CategorySpendRow
from core.queries import category_spend

router = APIRouter(tags=["categories"])


@router.get("/category-spend", response_model=list[CategorySpendRow])
def category_spend_route(
    session: Session = Depends(get_session),
    start_date: date_t = Query(...),
    end_date: date_t = Query(...),
) -> list[CategorySpendRow]:
    return [CategorySpendRow(**row) for row in category_spend(session, start_date=start_date, end_date=end_date)]
```

- [ ] **Step 8: Mount the 5 new routers in `api/main.py`**

In `api/main.py`, after the plaid import line inside `create_app()`, add:

```python
    from api.routes import (
        accounts as accounts_routes,
        transactions as transactions_routes,
        holdings as holdings_routes,
        networth as networth_routes,
        categories as categories_routes,
    )
    app.include_router(accounts_routes.router)
    app.include_router(transactions_routes.router)
    app.include_router(holdings_routes.router)
    app.include_router(networth_routes.router)
    app.include_router(categories_routes.router)
```

- [ ] **Step 9: Run tests**

```bash
.venv/bin/pytest tests/api/test_read_routes.py -v
```

Expected: 6 passed.

- [ ] **Step 10: Commit**

```bash
git add api/routes/{accounts,transactions,holdings,networth,categories}.py \
        api/main.py tests/api/test_read_routes.py
git commit -m "feat(api): read routes (accounts, transactions, holdings, networth, categories) (Plan 4, Task 3)"
```

---

## Task 4: Sync routes (POST /sync, GET /sync/status) + startup hook

**Files:**
- Create: `api/routes/sync.py`
- Modify: `api/main.py` (startup hook + mount sync router)
- Create: `tests/api/test_sync_routes.py`
- Create: `tests/api/test_startup.py`

- [ ] **Step 1: Write `api/routes/sync.py`**

```python
"""Sync routes — kick off and observe sync runs.

POST /sync   — schedule a background sync of every linked Item.
GET  /sync/status — return current Item statuses.
"""
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_plaid_client, get_session, get_session_factory
from api.schemas import SyncStartedOut, SyncStatusOut
from core.db import Institution, Item
from core.plaid.orchestrator import sync_all_items

router = APIRouter(tags=["sync"])


def _list_item_ids(session: Session) -> list[str]:
    return [row[0] for row in session.execute(select(Item.item_id)).all()]


def _run_sync(item_ids: list[str], plaid_client_factory, session_factory) -> None:
    """Helper: runs in a background thread, drives the orchestrator."""
    sync_all_items(
        client_factory=plaid_client_factory,
        session_factory=session_factory,
        item_ids=item_ids,
    )


@router.post("/sync", response_model=SyncStartedOut)
def sync_route(
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> SyncStartedOut:
    item_ids = _list_item_ids(session)
    if item_ids:
        # Build factories that don't depend on FastAPI's per-request session.
        from api.deps import get_plaid_client as _get_client
        background_tasks.add_task(
            _run_sync,
            item_ids,
            _get_client,
            get_session_factory(),
        )
    return SyncStartedOut(started=bool(item_ids), item_count=len(item_ids))


@router.get("/sync/status", response_model=list[SyncStatusOut])
def sync_status_route(
    session: Session = Depends(get_session),
) -> list[SyncStatusOut]:
    stmt = (
        select(Item, Institution)
        .join(Institution, Institution.institution_id == Item.institution_id)
        .order_by(Institution.name)
    )
    out = []
    for item, inst in session.execute(stmt).all():
        out.append(
            SyncStatusOut(
                item_id=item.item_id,
                institution_name=inst.name,
                last_sync_status=item.last_sync_status,
                last_sync_error=item.last_sync_error,
                last_sync_at=item.last_sync_at.isoformat() if item.last_sync_at else None,
            )
        )
    return out
```

- [ ] **Step 2: Mount the sync router in `api/main.py`**

After the other `app.include_router(...)` calls, add:

```python
    from api.routes import sync as sync_routes
    app.include_router(sync_routes.router)
```

- [ ] **Step 3: Add startup hook to `api/main.py`**

Replace the entire `api/main.py` with:

```python
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
```

The test client in `tests/api/conftest.py` should already set `FINANCE_TRACKER_SKIP_STARTUP=1` to prevent migrations / sync from running during tests. Update the conftest:

In `tests/api/conftest.py`, before `@pytest.fixture\ndef client(...)`, add:

```python
import os
os.environ["FINANCE_TRACKER_SKIP_STARTUP"] = "1"
```

(Top of the file, after imports.)

- [ ] **Step 4: Write `tests/api/test_sync_routes.py`**

```python
def test_post_sync_returns_started_and_item_count(client, seeded_chain):
    resp = client.post("/sync")
    assert resp.status_code == 200
    body = resp.json()
    assert body["started"] is True
    assert body["item_count"] == 1


def test_post_sync_with_no_items_returns_started_false(client):
    resp = client.post("/sync")
    body = resp.json()
    assert body["started"] is False
    assert body["item_count"] == 0


def test_get_sync_status_lists_each_item(client, seeded_chain):
    resp = client.get("/sync/status")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["item_id"] == "item_test"
    assert body[0]["institution_name"] == "Test Bank"
```

- [ ] **Step 5: Write `tests/api/test_startup.py`**

```python
"""Smoke test that the app boots cleanly with the startup hook skipped."""


def test_health_returns_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

- [ ] **Step 6: Run tests**

```bash
.venv/bin/pytest tests/api/ -v
```

Expected: all api tests pass (3 plaid + 6 read + 3 sync + 1 health = 13).

- [ ] **Step 7: Commit**

```bash
git add api/routes/sync.py api/main.py tests/api/test_sync_routes.py tests/api/test_startup.py tests/api/conftest.py
git commit -m "feat(api): /sync and /sync/status routes + startup hook (Plan 4, Task 4)"
```

---

## Task 5: Makefile + macOS desktop launcher

**Files:**
- Create: `Makefile`
- Create: `scripts/finance-tracker.command`
- Create symlink: `~/Desktop/Finance Tracker.command` → `scripts/finance-tracker.command`

- [ ] **Step 1: Write `Makefile`**

Write to `Makefile`:

```makefile
.PHONY: dev test migrate clean help

VENV := .venv
PYTHON := $(VENV)/bin/python
UVICORN := $(VENV)/bin/uvicorn
ALEMBIC := $(VENV)/bin/alembic
PYTEST := $(VENV)/bin/pytest

help:
	@echo "Targets:"
	@echo "  make dev      — run uvicorn (Plan 5 will add Vite alongside)"
	@echo "  make test     — run the full test suite"
	@echo "  make migrate  — run alembic upgrade head"
	@echo "  make clean    — remove .pyc files and pytest cache"

dev:
	@echo "Starting Finance Tracker on http://localhost:8000 (Ctrl-C to stop)"
	$(UVICORN) api.main:app --host 127.0.0.1 --port 8000 --reload

test:
	$(PYTEST) -v

migrate:
	$(ALEMBIC) upgrade head

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	rm -rf .pytest_cache htmlcov .coverage
```

- [ ] **Step 2: Write `scripts/finance-tracker.command`**

Write to `scripts/finance-tracker.command`:

```bash
#!/bin/bash
# macOS double-clickable launcher for Finance Tracker.
# Symlinked to ~/Desktop/Finance Tracker.command.

set -e
PROJECT="/path/to/house_of_hearth"

cd "$PROJECT"
echo "Finance Tracker — starting..."
exec make dev
```

Make it executable:

```bash
chmod +x scripts/finance-tracker.command
```

- [ ] **Step 3: Symlink to ~/Desktop**

```bash
ln -sf "/path/to/house_of_hearth/scripts/finance-tracker.command" \
       "$HOME/Desktop/Finance Tracker.command"
```

Verify:

```bash
ls -la "$HOME/Desktop/Finance Tracker.command"
```

Expected: a symlink pointing at the project's `scripts/finance-tracker.command`.

If `$HOME/Desktop/Finance Tracker.command` already exists (e.g., the user manually placed something), back it up first:

```bash
[ -e "$HOME/Desktop/Finance Tracker.command" ] && \
  mv "$HOME/Desktop/Finance Tracker.command" "$HOME/Desktop/Finance Tracker.command.bak"
```

- [ ] **Step 4: Smoke test the Makefile (without actually starting uvicorn)**

```bash
make help
```

Expected: prints the help text.

```bash
make test 2>&1 | tail -3
```

Expected: full suite passes (~106 tests).

- [ ] **Step 5: Commit**

```bash
git add Makefile scripts/finance-tracker.command
git commit -m "feat(launcher): make dev target + macOS desktop .command file (Plan 4, Task 5)"
```

The `~/Desktop/Finance Tracker.command` symlink is OUTSIDE the project — git won't track it (and shouldn't).

---

## Plan 4 Verification

```bash
.venv/bin/pytest -v --tb=no -q | tail -5
```

Expected: ~106 passed (93 from Plan 3 + ~13 from Plan 4) + 1 skipped.

Manual smoke (do NOT run automatically — the user runs this when ready):

1. `make dev` → opens uvicorn on `localhost:8000`.
2. Browse `localhost:8000/docs` → see the OpenAPI/Swagger UI for every route.
3. `curl http://localhost:8000/health` → `{"status": "ok"}`.
4. `curl http://localhost:8000/networth` → `{"total": 0, ...}` (no data yet).

---

## Hand-off to Plan 5

Plan 5 (Frontend) will:
- Add `frontend/` (Vite + React + Tailwind + TanStack Query + react-plaid-link).
- Add 4 pages: Dashboard, Transactions, Accounts, Holdings.
- Update the Makefile's `dev` target to run uvicorn + Vite together (using a Python supervisor or `concurrently`).
