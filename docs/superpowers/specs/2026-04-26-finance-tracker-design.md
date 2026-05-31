# Personal Finance Tracker — Design

**Status:** approved (brainstorming) — pending implementation plan
**Date:** 2026-04-26
**Owner:** Kandel-Bibas

## 1. Goals

Self-hosted personal finance tracker. Pulls transactions, balances, and investment holdings from linked bank/credit/brokerage accounts via Plaid. Provides:

- A local web UI for net worth, cash flow, category breakdown, and a filterable transaction list.
- A local MCP server exposing read-only query tools so Claude (Desktop, Code) can answer questions about the user's finances.

Single user. Runs only when the user opens it. No cloud hosting.

## 2. Constraints and decisions

The following were locked during brainstorming. They are inputs to this design, not open for re-litigation:

| Decision | Choice | Rationale |
|---|---|---|
| Hosting | Local only (no Vercel / no public ingress) | Plaid access tokens grant bank-read access; cloud storage would require a much larger security investment. |
| Sync model | On-demand only; auto-runs at app open | The app is not continuously running; Plaid's `/transactions/sync` cursor catches up incrementally on next open. |
| MCP scope | Read-only DB query tools | No write actions, no Plaid calls from MCP. Smallest possible surface for an agent. |
| Process model | `make dev` launched from a desktop `.command` file | Backend (FastAPI) + frontend (Vite) start in one parallelized command. MCP launched separately by Claude Desktop via stdio. |
| Secrets posture | macOS Keychain master key + AES-GCM encryption of access tokens in SQLite | A leaked `finance.db` file is useless without macOS login; encryption surface is small. |
| Holdings/balance history | Current snapshot only (overwrite each sync) | Net worth chart shows changes only when transactions occur. Reversible later by adding a snapshots table. |
| Repo structure | Layered monorepo: `core/`, `api/`, `mcp/`, `frontend/` | Two consumers (FastAPI, MCP) read the same data; a shared pure-Python `core` keeps logic in one place. |
| Data sources | Plaid only | Fidelity / manual CSV explicitly out of scope for v1. |

## 3. Out of scope

- Multi-user / authentication. App is single-user; no login wall.
- Production Plaid environment. Development env covers the user's accounts.
- Mobile app.
- Webhooks. No public ingress, no tunnel.
- Fidelity / manual CSV import.
- Investment transactions (`/investments/transactions/get`). Holdings + balances only.
- Multi-currency conversion (assumed USD; revisit if a non-USD account is linked).
- Transaction edit / manual recategorization UI. Additive later.
- Cloud deployment. Schema is portable to Postgres if remote hosting becomes a real need.

## 4. Architecture

```
┌────────────────────────────────────────────────────────────────┐
│  User (browser at localhost:5173, double-clicked .command)     │
└──────────────┬─────────────────────────────────────────────────┘
               │ HTTP (JSON)
               ▼
   ┌───────────────────────┐               ┌─────────────────────┐
   │  api/  (FastAPI)      │               │  mcp/  (stdio)      │
   │  /plaid/link-token    │               │  search_txns        │
   │  /plaid/exchange      │               │  net_worth          │
   │  /sync (auto+manual)  │               │  category_spend     │
   │  /accounts /txns ...  │               │  list_holdings      │
   └───────────┬───────────┘               └──────────┬──────────┘
               │                                      │
               └───────────────┬──────────────────────┘
                               ▼
                  ┌─────────────────────────┐
                  │  core/  (pure Python)   │
                  │  ┌───────────────────┐  │   ┌───────────────────┐
                  │  │ plaid             │──┼──►│  Plaid API (dev)  │
                  │  └───────────────────┘  │   └───────────────────┘
                  │  ┌───────────────────┐  │   ┌───────────────────┐
                  │  │ crypto            │──┼──►│  macOS Keychain   │
                  │  └───────────────────┘  │   └───────────────────┘
                  │  ┌───────────────────┐  │
                  │  │ db                │──┼──► finance.db (SQLite WAL)
                  │  └───────────────────┘  │
                  │  ┌───────────────────┐  │
                  │  │ queries           │  │
                  │  └───────────────────┘  │
                  └─────────────────────────┘
```

### 4.1 Repository layout

```
finance-tracker/
├── core/
│   ├── db/                    # SQLAlchemy 2.x models, session, Alembic migrations
│   ├── plaid/                 # link, sync, holdings; wraps plaid-python
│   ├── crypto/                # Keychain access + AES-GCM token cipher
│   └── queries/               # read-side functions (used by api + mcp)
├── api/
│   └── routes/                # /plaid/*, /accounts, /transactions, /holdings, /networth, /sync
├── mcp/
│   └── tools/                 # one file per MCP tool, thin wrapper over core.queries
├── frontend/                  # Vite + React + Tailwind + TanStack Query + React Router
├── scripts/
│   ├── make-dev               # uvicorn + vite supervisor
│   └── Finance Tracker.command  # macOS double-clickable → make dev
├── Makefile
└── pyproject.toml             # one workspace, three Python entrypoints
```

### 4.2 Boot sequence

1. User double-clicks `Finance Tracker.command` on the desktop.
2. macOS opens Terminal, runs `make dev`.
3. Makefile launches `uvicorn` (FastAPI) and `pnpm dev` (Vite) in parallel via a Python supervisor process so Ctrl-C cleanly stops both.
4. FastAPI startup hook:
   - Run Alembic `upgrade head`.
   - Load master key from Keychain (silent after the one-time "Always Allow").
   - Schedule a non-blocking sync task per linked Item (`asyncio.gather(..., return_exceptions=True)`).
5. Vite opens browser tab at `localhost:5173`. UI renders against whatever is already in the DB; sync status pills update as background tasks finish.
6. MCP server is **not** started by `make dev`. Claude Desktop launches `python -m mcp` over stdio when an agent needs it.

## 5. Data flow

### 5.1 Linking a bank (one-time per institution)

1. User clicks "Add Account" in the frontend.
2. Frontend `POST /plaid/link-token` → backend calls `/link/token/create` with the user's Plaid client ID/secret → returns `link_token`.
3. Frontend opens Plaid Link iframe (`react-plaid-link`) with `link_token`.
4. User authenticates with their bank inside the iframe. Plaid's `onSuccess` returns a short-lived `public_token` to the frontend.
5. Frontend `POST /plaid/exchange { public_token }` → backend calls `/item/public_token/exchange` → receives `access_token`, `item_id`.
6. Backend encrypts `access_token` (AES-GCM, AAD = `item_id`), inserts rows into `institutions`, `items`, `accounts`, kicks off initial sync as a background task.

The long-lived `access_token` never leaves the backend.

### 5.2 Auto-sync on app open

For each linked Item, in parallel:

1. Decrypt the Item's `access_token`.
2. Loop `/transactions/sync` until `has_more = false`. Each page is one DB transaction:
   - Upsert `added` and `modified` by `transaction_id`.
   - Soft-delete `removed` (`SET removed_at = now()`).
   - Save `next_cursor` and `last_sync_at`.
3. Call `/accounts/get` to refresh balances. Overwrite `accounts.current_balance`, `available_balance`, `limit_balance`, `last_balance_at` for every account in this Item. (Plaid's `/transactions/sync` does **not** return balances; without this step, non-investment account balances drift after the initial link.)
4. If the Item contains at least one account with `type = 'investment'`: call `/investments/holdings/get`. Upsert `securities`, overwrite `holdings` rows for those accounts. Investment balances are also refreshed via this call (taking precedence over step 3 for those accounts).
5. Set `last_sync_status = 'ok'` or `'error'` with `last_sync_error` populated.

Manual `POST /sync` (the "Sync now" button) runs the same flow.

### 5.3 Frontend read

React pages mount → TanStack Query hooks call `GET /api/...` → `api/routes/*` calls `core.queries.*` → returns plain dicts (no SQLAlchemy objects across the boundary). TanStack caches by query key. A successful sync invalidates relevant cache keys.

No WebSocket / SSE. While a sync is active, the UI polls `GET /sync/status` every 2 seconds.

### 5.4 MCP query

Claude Desktop launches `python -m mcp` (stdio). The MCP server opens SQLite in read-only mode (`sqlite:///finance.db?mode=ro`). It does **not** import `core.crypto` and has no path to call Plaid.

At startup, MCP runs `alembic current` and checks it against `alembic heads`. If they differ (user upgraded the app but hasn't reopened it yet), MCP refuses to serve queries and returns a clear error to the agent ("schema out of date — open the app once to migrate"). MCP never runs migrations itself.

Tool call → `mcp/tools/<name>.py` → `core.queries.<fn>(...)` → JSON-safe dict → MCP tool result.

Tools (v1):

- `search_transactions(filters)` — date range, category, merchant, account, min/max amount.
- `net_worth(at_date?)` — sum of balances by account type, signed correctly.
- `category_spend(start, end)` — group by `category_primary` (and optionally `category_detailed`).
- `list_holdings()` — current positions across investment accounts.
- `list_accounts()` — linked accounts with masked numbers and last sync status.

## 6. Database schema

Single SQLite database (`finance.db`), WAL mode, six tables. Money stored as `REAL` (float). Migrations via Alembic.

### 6.1 Tables

**`institutions`**

| Column | Type | Notes |
|---|---|---|
| institution_id | TEXT PK | Plaid `ins_xxx` |
| name | TEXT | |
| logo | TEXT | base64 PNG |
| primary_color | TEXT | `#hex` |
| url | TEXT | |

**`items`**

| Column | Type | Notes |
|---|---|---|
| item_id | TEXT PK | Plaid item_id |
| institution_id | TEXT FK → institutions | |
| access_token_ciphertext | BLOB | nonce(12) ‖ ciphertext ‖ tag(16) |
| transactions_cursor | TEXT | nullable; opaque |
| last_sync_at | TIMESTAMP | |
| last_sync_status | TEXT | `ok` \| `error` \| `pending` |
| last_sync_error | TEXT | nullable |
| created_at | TIMESTAMP | |

**`accounts`**

| Column | Type | Notes |
|---|---|---|
| account_id | TEXT PK | Plaid account_id |
| item_id | TEXT FK → items | |
| name | TEXT | |
| official_name | TEXT | |
| type | TEXT | depository \| credit \| investment \| loan |
| subtype | TEXT | checking \| savings \| credit card \| brokerage \| ... |
| mask | TEXT | last 4 digits |
| current_balance | REAL | |
| available_balance | REAL | |
| limit_balance | REAL | nullable (credit limit) |
| iso_currency_code | TEXT | |
| last_balance_at | TIMESTAMP | |
| raw_payload | JSON | |

Index: `(item_id)`.

**`transactions`**

| Column | Type | Notes |
|---|---|---|
| transaction_id | TEXT PK | Plaid transaction_id |
| account_id | TEXT FK → accounts | |
| date | DATE | posted date |
| authorized_date | DATE | nullable |
| amount | REAL | Plaid sign convention: + outflow, − inflow |
| iso_currency_code | TEXT | |
| name | TEXT | raw description |
| merchant_name | TEXT | nullable, Plaid-cleaned |
| payment_channel | TEXT | in store \| online \| other |
| pending | BOOLEAN | |
| category_primary | TEXT | from `personal_finance_category.primary` |
| category_detailed | TEXT | from `personal_finance_category.detailed` |
| category_confidence | TEXT | VERY_HIGH \| HIGH \| MEDIUM \| LOW |
| raw_payload | JSON | full Plaid response |
| removed_at | TIMESTAMP | nullable; soft delete |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

Indexes: `(account_id, date DESC)`, `(date DESC)`, `(category_primary, date DESC)`, `(merchant_name)`, `(removed_at)`.

**`securities`**

| Column | Type | Notes |
|---|---|---|
| security_id | TEXT PK | Plaid security_id |
| ticker_symbol | TEXT | |
| name | TEXT | |
| type | TEXT | equity \| etf \| mutual fund \| cash \| ... |
| iso_currency_code | TEXT | |
| close_price | REAL | |
| close_price_as_of | DATE | |

**`holdings`**

| Column | Type | Notes |
|---|---|---|
| account_id | TEXT FK → accounts | |
| security_id | TEXT FK → securities | |
| quantity | REAL | |
| institution_price | REAL | |
| institution_value | REAL | quantity × price (Plaid-reported) |
| cost_basis | REAL | nullable |
| last_synced_at | TIMESTAMP | |

PK: `(account_id, security_id)`. Overwritten on each sync.

### 6.2 Schema-level decisions

- **No `users` table.** Single-user. One migration adds it later if needed.
- **No `categories` table.** Plaid's `personal_finance_category` taxonomy is fixed and small; treated as enum strings. Manual category overrides (future) become a nullable column on `transactions`, not a join.
- **`raw_payload` JSON columns** preserve everything Plaid returns (counterparties, location, payment_meta, owners) without normalizing into side tables. Queryable via `json_extract` if needed.
- **Money as `REAL`.** Adequate for personal-scale data. If pennies-perfect accounting matters later, migrate to integer cents.
- **WAL mode.** FastAPI opens read-write; MCP opens read-only (`?mode=ro`). Concurrent reads, no lock contention.

## 7. Encryption and sync details

### 7.1 Encryption

**Master key**

- 32 random bytes (`os.urandom`), generated on first launch ever.
- Stored in macOS Keychain via `keyring`: service `finance-tracker`, account `master-key`, value base64-encoded.
- First read prompts the user once with "Always Allow" (or Touch ID). Silent thereafter for the same Python binary.
- Never written to disk; lives only in process memory while the app runs.

**Per-token encryption**

- Library: `cryptography.hazmat.primitives.ciphers.aead.AESGCM`.
- Per token: 12-byte random nonce (per-token, never reused), AAD = `item_id` bytes, ciphertext = `AESGCM(key).encrypt(nonce, token.encode(), aad)`.
- On-disk format: `nonce(12) ‖ ciphertext ‖ tag(16)` in a single `BLOB` column.
- AAD binding ensures a ciphertext cannot be moved between rows.

**What is not encrypted**

Transactions, holdings, account names, balances, and institution metadata are not credentials. Encrypting them would prevent SQL queries; the threat model (laptop stolen with FileVault on) does not justify it.

**Key rotation (deferred)**

`core.crypto.rotate_master_key()` will decrypt all access tokens with the old key, generate a new key, re-encrypt, swap the Keychain entry inside one DB transaction. Not v1.

### 7.2 Sync error handling

| Plaid error | Behavior |
|---|---|
| `ITEM_LOGIN_REQUIRED` | Mark error; UI shows "Reconnect" → triggers Plaid Link in update mode. |
| `INSTITUTION_DOWN` / `INSTITUTION_NOT_RESPONDING` | Mark error; cursor untouched; retry next run. |
| `PRODUCT_NOT_READY` | Sleep 30s, retry up to 5× within the run. |
| `RATE_LIMIT_EXCEEDED` | Exponential backoff: 1s, 2s, 4s, 8s, 16s, then give up for this run. |
| `INVALID_ACCESS_TOKEN` | Mark error; UI prompts re-link (creates a new Item). |
| Anything else | Capture code + message in `last_sync_error`, mark error, continue with next Item. |

Items run as `asyncio.gather(*tasks, return_exceptions=True)`. One Item failing never blocks another.

### 7.3 Cursor atomicity

Plaid `/transactions/sync` returns `{added, modified, removed, has_more, next_cursor}`. The invariant: a cursor advance is committed only with the rows that justify it.

```python
async def apply_sync_page(item, page):
    async with db.transaction():
        upsert_added(page.added)
        upsert_modified(page.modified)
        soft_delete(page.removed)
        item.transactions_cursor = page.next_cursor
        item.last_sync_at = utcnow()
```

If anything in the block raises, SQLite rolls back. Cursor stays put. Next sync replays the same page idempotently (upserts keyed by `transaction_id`).

Each page = one DB transaction. A 500-page Item that fails on page 487 keeps 1–486 committed and resumes at 487.

### 7.4 Concurrency

- Per-Item `asyncio.Lock` so manual sync cannot race auto-sync.
- No cross-process locks. SQLite WAL handles multi-reader/single-writer. MCP is read-only by construction.

## 8. Testing approach

### 8.1 Heavily tested

- **`core/crypto`** — round-trip, AAD binding (cross-item ciphertext rejection), nonce uniqueness, mocked Keychain.
- **`core/plaid/sync`** — atomicity (mid-page failure leaves cursor unchanged), idempotency (replay = same end state), soft-delete semantics, modification overwrites, multi-page pagination, Plaid error → status mapping.
- **`core/queries`** — filter correctness, net worth signing across account types, exclusion of soft-deleted rows, holdings join + value totals.

### 8.2 Lightly tested

- **`api/`** — one happy-path test per route via FastAPI `TestClient`. Routes are thin; logic is in `core`.
- **`mcp/`** — one test per tool that invokes it and checks JSON shape.

### 8.3 Hand-tested only

- **`frontend/`** — no Vitest suite for v1.
- **End-to-end (Playwright + Plaid Link)** — skipped. Plaid Link's iframe is hard to drive headlessly; manual smoke test is fast.

### 8.4 Test infrastructure

- `pytest` + `pytest-asyncio` + `pytest-cov`. Coverage target 80%+ for `core/`; no target on glue layers.
- `conftest.py` provides per-test in-memory SQLite with full Alembic upgrade applied + seed factories.
- Integration tests against Plaid **Sandbox** (`PLAID_ENV=sandbox`, `user_good`/`pass_good`), never Development. A test config pins the env var.
- No CI for v1. `make test` runs locally.

### 8.5 Implementation order

1. `core/crypto` + tests (small, self-contained, corruption here is permanent).
2. `core/db` models + Alembic baseline (no tests; schema is data).
3. `core/plaid/sync` + tests in lockstep (cursor invariant verified by tests, not inspection).
4. `core/queries` + tests (after enough fixture data exists for meaningful assertions).
5. `api/` routes + `mcp/` tools (one happy-path test each, written alongside).
6. `frontend/` last, no tests.

## 9. Future work (explicit, deferred)

- Investment transactions (`/investments/transactions/get`).
- Daily holdings/balance snapshots → real net-worth-over-time chart.
- Webhook receiver behind a tunnel (only if remote-agent freshness ever matters).
- Manual transaction recategorization UI + override column.
- Fidelity / manual CSV import.
- Master key rotation utility.
- Postgres migration (only if cloud hosting becomes a real need).
- Splitwise push tool on the MCP server (write action — needs explicit per-call confirmation pattern).
