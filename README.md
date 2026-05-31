# House of Hearth

> A local-first personal finance tracker you can also **ask in plain English** — built around Plaid, FastAPI, React, and a read-only [MCP](https://modelcontextprotocol.io) server that lets Claude answer questions about your money.

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-WAL-003B57?logo=sqlite&logoColor=white)
![MCP](https://img.shields.io/badge/MCP-read--only-7C3AED)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

**[🔥 Live site](https://kandel-bibas.github.io/House_of_Hearth/) · [Quick start](#quick-start) · [Connect Claude (MCP)](docs/MCP_SETUP.md)**

House of Hearth links your bank, credit, and brokerage accounts through [Plaid](https://plaid.com), stores everything in a single local SQLite file, and gives you two ways to explore it: a React dashboard (net worth, cash flow, spending by category, a filterable transaction ledger, holdings) and a local MCP server that exposes read-only query tools to Claude Desktop. Nothing is hosted — it runs only when you open it, and your bank access tokens are encrypted at rest with a key kept in your OS keychain (macOS, Windows, or Linux).

---

## Highlights

- **Natural-language finance Q&A.** A local stdio MCP server exposes five read-only tools so you can ask Claude *"what did I spend on groceries last month?"* or *"what's my net worth?"* and get answers from your own data.
- **Secrets encrypted at rest.** Long-lived Plaid access tokens are sealed with AES-GCM (token bound to its `item_id` via AAD); the 32-byte master key lives in your OS keychain (macOS Keychain / Windows Credential Locker / Linux Secret Service), never on disk. A leaked `finance.db` is useless without your login.
- **Incremental sync with crash-resume.** Uses Plaid's `/transactions/sync` cursor, commits one page at a time, and soft-deletes removed transactions — a sync that dies on page 487 of 500 resumes cleanly instead of starting over.
- **Two consumers, one source of truth.** A pure-Python `core/` layer (db, crypto, Plaid, queries) is shared by both the FastAPI app and the MCP server, so query logic lives in exactly one place.
- **Least-privilege MCP surface.** The MCP server opens SQLite read-only (`?mode=ro`), never imports `core.crypto`, and has no path to Plaid. Worst case is "an agent reads your spending," never "an agent moves money."
- **Built test-first.** 117 tests (116 passing, 1 opt-in Plaid Sandbox test) span crypto, the DB layer, Plaid sync, the query layer, the HTTP API, and the MCP server, alongside Alembic migrations.

---

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│  You — browser at localhost:5173  +  Claude Desktop            │
└───────────────┬──────────────────────────────┬─────────────────┘
                │ HTTP (JSON)                   │ MCP (stdio)
                ▼                               ▼
   ┌───────────────────────┐         ┌─────────────────────┐
   │  api/  (FastAPI)      │         │  mcp_server/ (stdio)│
   │  /plaid/link-token    │         │  search_transactions│
   │  /plaid/exchange      │         │  net_worth          │
   │  /sync · /sync/status │         │  category_spend     │
   │  /accounts /transactions        │  list_holdings      │
   │  /holdings /networth  │         │  list_accounts      │
   │  /category-spend      │         │  (SQLite read-only) │
   └───────────┬───────────┘         └──────────┬──────────┘
               │                                │
               └───────────────┬────────────────┘
                               ▼
                  ┌─────────────────────────┐
                  │  core/  (pure Python)   │
                  │  ┌───────────────────┐  │   ┌───────────────────┐
                  │  │ plaid             │──┼──►│  Plaid API        │
                  │  └───────────────────┘  │   └───────────────────┘
                  │  ┌───────────────────┐  │   ┌───────────────────┐
                  │  │ crypto            │──┼──►│  OS keychain      │
                  │  └───────────────────┘  │   └───────────────────┘
                  │  ┌───────────────────┐  │
                  │  │ db (SQLAlchemy)   │──┼──► finance.db (SQLite, WAL)
                  │  └───────────────────┘  │
                  │  ┌───────────────────┐  │
                  │  │ queries           │  │
                  │  └───────────────────┘  │
                  └─────────────────────────┘
```

| Layer | Responsibility |
|---|---|
| `core/db` | SQLAlchemy 2.x models for 6 tables, engine factory (WAL + foreign-key pragmas), Alembic migrations |
| `core/crypto` | OS-keychain master-key access (cross-platform via `keyring`) + AES-GCM token cipher |
| `core/plaid` | Plaid client factory, Link flow, cursor sync, balance/holdings refresh, error classification, orchestrator |
| `core/queries` | Read-only query functions (`net_worth`, `search_transactions`, `category_spend`, `list_holdings`, `list_accounts`) returning JSON-safe dicts |
| `api/` | FastAPI routes that wrap `core/`; runs migrations + background auto-sync on startup |
| `mcp_server/` | FastMCP stdio server exposing the five query functions as read-only tools |
| `frontend/` | React 19 + Vite SPA (dashboard, accounts, transactions, holdings) |

The full design rationale and data model live in [`docs/superpowers/specs/2026-04-26-finance-tracker-design.md`](docs/superpowers/specs/2026-04-26-finance-tracker-design.md).

---

## Tech stack

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.0, Alembic, Uvicorn, SQLite (WAL mode)
- **Banking data:** Plaid (`plaid-python`) — Link, `/transactions/sync`, balances, investment holdings
- **Security:** `cryptography` (AES-GCM), `keyring` (cross-platform OS keychain)
- **AI integration:** Model Context Protocol via `mcp` (FastMCP)
- **Frontend:** React 19, TypeScript, Vite, Tailwind CSS v4, shadcn/ui, TanStack Query, React Router, Recharts, `react-plaid-link`
- **Tooling & tests:** pytest (+ `pytest-cov`, `httpx`), a Makefile, and a Python dev supervisor that runs the API and Vite together

---

## Prerequisites

- **An OS keychain** — macOS Keychain, Windows Credential Locker, or Linux Secret Service (GNOME Keyring/KWallet). Built and tested on macOS; the secrets layer is cross-platform via the `keyring` library.
- **Python 3.11+**
- **Node.js 18+** and **pnpm** (`npm install -g pnpm`)
- A **Plaid account** for API keys — the free [Sandbox](https://plaid.com/docs/sandbox/) tier is enough to try everything

---

## Quick start

```bash
git clone https://github.com/Kandel-Bibas/House_of_Hearth.git
cd House_of_Hearth
```

### 1. Backend

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

> Prefer [uv](https://github.com/astral-sh/uv)? `uv venv && uv pip install -e ".[dev]"` works too — a `uv.lock` is committed.

Create your local `.env` from the template and add your Plaid keys:

```bash
cp .env.example .env
# then edit .env:
#   PLAID_ENV=sandbox
#   PLAID_CLIENT_ID=your_client_id
#   PLAID_SECRET=your_sandbox_secret
#   DATABASE_URL=sqlite:///finance.db
```

Apply the database migrations (the API also runs this automatically on startup):

```bash
make migrate
```

### 2. Frontend

```bash
cd frontend
pnpm install
cd ..
```

### 3. Run it

```bash
make dev
```

This starts the API on **http://localhost:8000** and the Vite dev server on **http://localhost:5173**. Open the second URL in your browser. `Ctrl-C` stops both.

> On first run, macOS will prompt once to allow access to the Keychain item — choose **Always Allow** so future syncs are silent.

> **Windows / Linux:** it runs the same way — the master key is stored in the Windows Credential Locker or the Linux Secret Service (GNOME Keyring/KWallet) instead of the macOS Keychain, via the cross-platform `keyring` library. The only macOS-only convenience is the double-click `scripts/finance-tracker.command` launcher; elsewhere just use `make dev`. (Most Linux desktops ship a Secret Service backend; headless servers may need one configured.)

---

## Getting Plaid keys (Sandbox)

1. Sign up at [dashboard.plaid.com](https://dashboard.plaid.com/signup) and grab your **client ID** and **Sandbox secret** from *Team Settings → Keys*.
2. Put them in `.env` with `PLAID_ENV=sandbox`.
3. In the app, click **Add Account**, pick any institution, and use Plaid's sandbox credentials: username `user_good`, password `pass_good` (and `1234` for any MFA prompt).
4. Click **Sync** — sandbox transactions, balances, and holdings flow into your local DB.

See Plaid's [Sandbox docs](https://plaid.com/docs/sandbox/test-credentials/) for more test institutions and scenarios.

---

## Connecting Claude Desktop (MCP)

The MCP server is a local stdio process that Claude Desktop launches on demand. Add an entry to `~/Library/Application Support/Claude/claude_desktop_config.json` pointing at this repo's `.venv` Python and the `mcp_server` module, then restart Claude Desktop and ask *"what MCP tools do you have?"*.

Full step-by-step instructions, troubleshooting, and the security rationale are in **[`docs/MCP_SETUP.md`](docs/MCP_SETUP.md)**.

---

## Usage

1. **Link an account** — *Add Account* opens Plaid Link; authenticate with your bank (or sandbox credentials).
2. **Sync** — the app auto-syncs linked accounts on launch; *Sync* triggers it manually. Status pills show progress per institution.
3. **Explore** — Dashboard (net worth, cash, investments, spend-by-category chart), Accounts (with drill-down), Transactions (date/category/merchant/amount filters), Holdings.
4. **Ask Claude** — with the MCP server wired up, ask things like *"what were my five biggest expenses in April?"* or *"how much do I hold in equities?"*.

---

## Project structure

```
house_of_hearth/
├── core/                       # pure-Python, shared by api/ and mcp_server/
│   ├── db/                     # SQLAlchemy models, session/engine, migrations target
│   ├── crypto/                 # macOS Keychain + AES-GCM token cipher
│   ├── plaid/                  # client, link, sync, refresh, errors, orchestrator
│   └── queries/                # read-side functions (net_worth, search_transactions, ...)
├── api/                        # FastAPI app
│   ├── main.py                 # app factory; startup runs migrations + auto-sync
│   ├── deps.py                 # engine/session/Plaid-client dependencies
│   ├── schemas.py              # Pydantic response models
│   └── routes/                 # plaid, accounts, transactions, holdings, networth, categories, sync
├── mcp_server/                 # FastMCP stdio server (5 read-only tools)
├── frontend/                   # React 19 + Vite + Tailwind + shadcn/ui SPA
├── migrations/                 # Alembic versions
├── scripts/
│   ├── run-dev.py              # supervisor: uvicorn + Vite together
│   └── finance-tracker.command # macOS double-click launcher
├── tests/                      # pytest suite (crypto, db, plaid, queries, api, mcp_server)
├── docs/                       # MCP setup + design spec/plans
├── Makefile
└── pyproject.toml
```

---

## HTTP API

Base URL: `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs` when the API is running.

| Method | Path | Description |
|---|---|---|
| `POST` | `/plaid/link-token` | Create a Plaid Link token to start the connect flow |
| `POST` | `/plaid/exchange` | Exchange a public token for an access token; persists the linked item |
| `GET`  | `/accounts` | Linked accounts with balances and sync status |
| `GET`  | `/transactions` | Filterable transactions (date, account, category, merchant, amount, limit) |
| `GET`  | `/holdings` | Current investment positions |
| `GET`  | `/networth` | Total net worth + breakdown by account type |
| `GET`  | `/category-spend` | Outflow grouped by primary category (`start_date`, `end_date` required) |
| `POST` | `/sync` | Kick off a background sync of all linked items |
| `GET`  | `/sync/status` | Per-item sync status |
| `GET`  | `/health` | Liveness check |

---

## MCP tools

The MCP server exposes the read-only query layer to Claude. All open SQLite in read-only mode.

| Tool | Description |
|---|---|
| `search_transactions(...)` | Filtered transaction list (dates, account, category, merchant, amount, limit) |
| `net_worth()` | Total plus per-account-type breakdown |
| `category_spend(start_date, end_date)` | Outflow by primary category |
| `list_holdings()` | Current investment positions |
| `list_accounts()` | Linked accounts with masked numbers and last sync status |

---

## Testing

```bash
make test            # full suite (network-touching Plaid tests are skipped by default)
pytest -m sandbox    # opt-in: run the Plaid Sandbox integration test (needs PLAID_* in env)
pytest --cov=core    # coverage for the core layer
```

The suite is **117 tests** (116 passing, 1 skipped) across the crypto, db, Plaid, queries, API, and MCP layers. The single skip is a Plaid Sandbox integration test gated behind the `sandbox` marker, so the default run is offline and deterministic.

---

## Security model

This is a single-user, local-only app, and the security design reflects that:

- **Local only.** No cloud hosting, no public ingress, no webhooks. The app runs only when you open it.
- **Encrypted access tokens.** Plaid access tokens (which grant bank-read access) are stored AES-GCM-encrypted in `finance.db`, bound to their `item_id` via the cipher's AAD. The 32-byte master key is held in your **OS keychain** — macOS Keychain, Windows Credential Locker, or Linux Secret Service — never written to disk, so a copied `finance.db` is inert without your OS login.
- **Read-only AI surface.** The MCP server opens SQLite with `?mode=ro`, never imports `core.crypto`, and cannot reach Plaid. It also refuses to serve queries if the DB schema is behind the latest migration, rather than risk stale results.
- **Secrets stay out of git.** `.env`, `*.db`, and the WAL/SHM sidecars are gitignored.

---

## Design decisions & scope

Locked decisions (see the [design spec](docs/superpowers/specs/2026-04-26-finance-tracker-design.md) for full rationale):

- **Local-first**, because Plaid access tokens are sensitive enough that cloud storage would demand a far larger security investment.
- **On-demand sync** (auto-runs on app open) — the app isn't always running; Plaid's cursor catches up incrementally.
- **Cross-platform secrets, macOS-first dev** — the secrets layer uses the cross-platform `keyring` library (macOS Keychain / Windows Credential Locker / Linux Secret Service). Built and tested on macOS; the only macOS-specific piece is the double-click `.command` launcher.
- **Single-user**, no auth wall.
- **Current-snapshot balances** — holdings/balances overwrite each sync; the schema is ready to add a history table later.

**Out of scope (v1):** multi-user/auth, cloud deployment, mobile, manual CSV import, investment transactions, multi-currency conversion. The SQLite schema is portable to Postgres if remote access ever becomes a real need.

---

## License

[MIT](LICENSE)
