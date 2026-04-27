# Plan 5 — Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** Add `frontend/` (Vite + React + TS + Tailwind v4 + TanStack Query + react-plaid-link + React Router) with 4 pages: Dashboard, Transactions, Accounts (with Add Account flow), Holdings. Update the Makefile to run uvicorn + Vite concurrently.

**Architecture:** SPA hitting the FastAPI backend on `localhost:8000`. TanStack Query handles server state with cache invalidation on sync. Tailwind for styling (v4 with Vite plugin). React Router v6 for navigation. The Plaid Link iframe runs via `react-plaid-link` — frontend gets a `link_token` from the API, opens the iframe, sends the resulting `public_token` back.

**Tech Stack:** Node 20+, pnpm (or npm), Vite 6, React 18, TypeScript 5, Tailwind v4, TanStack Query v5, React Router v6, react-plaid-link, lucide-react (icons). No tests for the frontend — manual smoke per the design spec.

**Spec reference:** `docs/superpowers/specs/2026-04-26-finance-tracker-design.md` — section 4.1 (frontend layout), section 5.1 (Link flow), section 5.3 (read flow), section 8.3 (no Vitest).

---

## File Structure

```
frontend/
├── index.html
├── package.json
├── tsconfig.json
├── tsconfig.node.json
├── vite.config.ts
├── postcss.config.js              # not needed for Tailwind v4 — using @tailwindcss/vite
├── public/
│   └── (favicon, eventually)
└── src/
    ├── main.tsx                   # ReactDOM.createRoot, QueryClient, Router
    ├── App.tsx                    # AppShell with sidebar + Outlet
    ├── index.css                  # Tailwind import + base styles
    ├── api/
    │   ├── client.ts              # fetch wrapper with base URL
    │   └── queries.ts             # TanStack Query hooks: useAccounts, useTransactions, useNetWorth, useHoldings, useCategorySpend, useSyncStatus
    ├── components/
    │   ├── Sidebar.tsx
    │   ├── SyncButton.tsx          # POST /sync + show status
    │   ├── AddAccountButton.tsx    # react-plaid-link integration
    │   ├── Money.tsx               # currency formatter
    │   └── DateRangeFilter.tsx
    └── pages/
        ├── Dashboard.tsx
        ├── Transactions.tsx
        ├── Accounts.tsx
        └── Holdings.tsx

Makefile                            # updated `dev` target runs uvicorn + vite together
scripts/run-dev.py                  # Python supervisor (Ctrl-C kills both)
```

---

## Task 1: Vite scaffold + Tailwind + deps

**Files:** `frontend/*` initial scaffold; `Makefile` not yet touched.

- [ ] **Step 1: Check Node availability**

```bash
which node && node --version
which pnpm || which npm
```

If `pnpm` isn't installed: use `npm` instead in the commands below. Document the choice in the status report.

If Node itself is missing, BLOCK and report — the user needs to install Node 20+ via Homebrew or nvm.

- [ ] **Step 2: Scaffold the Vite project**

```bash
cd /Users/bibas/personal/finance-tracker
# Use the React + TS template. -- separates pnpm/npm args from create-vite args.
pnpm create vite frontend --template react-ts || npm create vite@latest frontend -- --template react-ts
```

If interactive prompts appear: answer `react` then `react-ts`. If pnpm/npm versions differ in flag handling, use `npx create-vite@latest frontend --template react-ts` as a fallback.

After this, `frontend/` should contain: `package.json`, `tsconfig.json`, `vite.config.ts`, `src/main.tsx`, `src/App.tsx`, `index.html`.

- [ ] **Step 3: Add deps**

```bash
cd frontend
pnpm add @tailwindcss/vite tailwindcss \
         @tanstack/react-query react-router-dom \
         react-plaid-link lucide-react \
         clsx \
  || npm install @tailwindcss/vite tailwindcss \
                 @tanstack/react-query react-router-dom \
                 react-plaid-link lucide-react \
                 clsx
```

Tailwind v4 uses a Vite plugin (`@tailwindcss/vite`); no postcss config needed.

- [ ] **Step 4: Configure Vite for Tailwind**

Replace `frontend/vite.config.ts` with:

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    strictPort: true,
  },
});
```

- [ ] **Step 5: Tailwind base styles**

Replace `frontend/src/index.css` with:

```css
@import "tailwindcss";

@layer base {
  body {
    @apply bg-gray-50 text-gray-900 antialiased;
  }
}
```

- [ ] **Step 6: Replace `frontend/src/App.tsx` with a placeholder**

```tsx
export default function App() {
  return (
    <div className="min-h-screen flex items-center justify-center">
      <h1 className="text-3xl font-bold">Finance Tracker</h1>
    </div>
  );
}
```

- [ ] **Step 7: Confirm Vite dev server boots cleanly (then stop it)**

```bash
cd /Users/bibas/personal/finance-tracker/frontend
timeout 6 pnpm dev 2>&1 | head -20 || true
```

(Or use `npm run dev`.) Expected: a line like `Local:   http://localhost:5173/`. The `timeout 6` ensures we don't hang the agent. Don't actually browse — just confirm the server starts without errors.

- [ ] **Step 8: Commit**

```bash
cd /Users/bibas/personal/finance-tracker
# .gitignore already excludes frontend/node_modules.
git add frontend/package.json frontend/tsconfig.json frontend/tsconfig.node.json \
        frontend/vite.config.ts frontend/index.html \
        frontend/src/main.tsx frontend/src/App.tsx frontend/src/index.css \
        frontend/src/vite-env.d.ts frontend/public 2>/dev/null
# Use `git add frontend` if specific paths fail (some scaffold layouts vary).
git add frontend
git commit -m "feat(frontend): vite + react + tailwind v4 scaffold (Plan 5, Task 1)"
```

`pnpm-lock.yaml` (or `package-lock.json`) IS committed. `frontend/node_modules/` is gitignored from earlier.

---

## Task 2: API client + Query provider + Router skeleton

**Files:**
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/queries.ts`
- Create: `frontend/src/components/Sidebar.tsx`
- Replace: `frontend/src/main.tsx`, `frontend/src/App.tsx`
- Create: `frontend/src/pages/Dashboard.tsx`, `Transactions.tsx`, `Accounts.tsx`, `Holdings.tsx` (placeholders)

- [ ] **Step 1: Create the API client**

Write to `frontend/src/api/client.ts`:

```typescript
const BASE_URL = "http://localhost:8000";

export async function apiGet<T>(path: string, params?: Record<string, string | number | boolean | undefined>): Promise<T> {
  const url = new URL(BASE_URL + path);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
    }
  }
  const resp = await fetch(url.toString());
  if (!resp.ok) {
    throw new Error(`GET ${path} failed: ${resp.status} ${await resp.text()}`);
  }
  return resp.json();
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const resp = await fetch(BASE_URL + path, {
    method: "POST",
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!resp.ok) {
    throw new Error(`POST ${path} failed: ${resp.status} ${await resp.text()}`);
  }
  return resp.json();
}

// Response types (mirror api/schemas.py).
export interface Account {
  account_id: string;
  name: string;
  official_name: string | null;
  type: string;
  subtype: string | null;
  mask: string | null;
  current_balance: number | null;
  available_balance: number | null;
  limit_balance: number | null;
  iso_currency_code: string | null;
  last_balance_at: string | null;
  item_id: string;
  institution_id: string;
  institution_name: string;
  institution_logo: string | null;
  institution_primary_color: string | null;
  last_sync_status: string | null;
  last_sync_error: string | null;
  last_sync_at: string | null;
}

export interface Transaction {
  transaction_id: string;
  account_id: string;
  date: string | null;
  authorized_date: string | null;
  amount: number;
  iso_currency_code: string | null;
  name: string;
  merchant_name: string | null;
  payment_channel: string | null;
  pending: boolean;
  category_primary: string | null;
  category_detailed: string | null;
  category_confidence: string | null;
  removed_at: string | null;
}

export interface Holding {
  account_id: string;
  account_name: string;
  security_id: string;
  ticker_symbol: string | null;
  security_name: string | null;
  security_type: string | null;
  quantity: number;
  institution_price: number | null;
  institution_value: number | null;
  cost_basis: number | null;
  iso_currency_code: string | null;
}

export interface NetWorth {
  total: number;
  depository: number;
  credit: number;
  investment: number;
  loan: number;
}

export interface CategorySpendRow {
  category_primary: string;
  total: number;
  count: number;
}

export interface SyncStatus {
  item_id: string;
  institution_name: string;
  last_sync_status: string | null;
  last_sync_error: string | null;
  last_sync_at: string | null;
}
```

- [ ] **Step 2: Create the query hooks**

Write to `frontend/src/api/queries.ts`:

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  apiGet,
  apiPost,
  Account,
  CategorySpendRow,
  Holding,
  NetWorth,
  SyncStatus,
  Transaction,
} from "./client";

export function useAccounts() {
  return useQuery<Account[]>({
    queryKey: ["accounts"],
    queryFn: () => apiGet<Account[]>("/accounts"),
  });
}

export function useTransactions(filters: Record<string, string | number | boolean | undefined>) {
  return useQuery<Transaction[]>({
    queryKey: ["transactions", filters],
    queryFn: () => apiGet<Transaction[]>("/transactions", filters),
  });
}

export function useNetWorth() {
  return useQuery<NetWorth>({
    queryKey: ["networth"],
    queryFn: () => apiGet<NetWorth>("/networth"),
  });
}

export function useHoldings() {
  return useQuery<Holding[]>({
    queryKey: ["holdings"],
    queryFn: () => apiGet<Holding[]>("/holdings"),
  });
}

export function useCategorySpend(start: string, end: string) {
  return useQuery<CategorySpendRow[]>({
    queryKey: ["category-spend", start, end],
    queryFn: () => apiGet<CategorySpendRow[]>("/category-spend", { start_date: start, end_date: end }),
    enabled: !!start && !!end,
  });
}

export function useSyncStatus() {
  return useQuery<SyncStatus[]>({
    queryKey: ["sync-status"],
    queryFn: () => apiGet<SyncStatus[]>("/sync/status"),
    refetchInterval: 5000,  // poll while sync may be running
  });
}

export function useStartSync() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiPost<{ started: boolean; item_count: number }>("/sync"),
    onSuccess: () => {
      // Invalidate everything that depends on synced data after a short delay.
      setTimeout(() => {
        qc.invalidateQueries({ queryKey: ["accounts"] });
        qc.invalidateQueries({ queryKey: ["transactions"] });
        qc.invalidateQueries({ queryKey: ["networth"] });
        qc.invalidateQueries({ queryKey: ["holdings"] });
        qc.invalidateQueries({ queryKey: ["category-spend"] });
        qc.invalidateQueries({ queryKey: ["sync-status"] });
      }, 3000);
    },
  });
}

export function useExchangePublicToken() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (publicToken: string) =>
      apiPost<{ item_id: string }>("/plaid/exchange", { public_token: publicToken }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["accounts"] });
      qc.invalidateQueries({ queryKey: ["sync-status"] });
    },
  });
}

export function useLinkToken() {
  return useMutation({
    mutationFn: () => apiPost<{ link_token: string }>("/plaid/link-token"),
  });
}
```

- [ ] **Step 3: Create the Sidebar**

Write to `frontend/src/components/Sidebar.tsx`:

```tsx
import { NavLink } from "react-router-dom";
import { LayoutDashboard, ListChecks, Wallet, TrendingUp } from "lucide-react";
import clsx from "clsx";

const items = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/transactions", label: "Transactions", icon: ListChecks },
  { to: "/accounts", label: "Accounts", icon: Wallet },
  { to: "/holdings", label: "Holdings", icon: TrendingUp },
];

export function Sidebar() {
  return (
    <nav className="w-56 shrink-0 border-r border-gray-200 bg-white p-4">
      <h1 className="text-xl font-semibold mb-6">Finance Tracker</h1>
      <ul className="flex flex-col gap-1">
        {items.map(({ to, label, icon: Icon }) => (
          <li key={to}>
            <NavLink
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                clsx(
                  "flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium",
                  isActive ? "bg-gray-900 text-white" : "text-gray-700 hover:bg-gray-100"
                )
              }
            >
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
```

- [ ] **Step 4: Replace `frontend/src/App.tsx`**

```tsx
import { Outlet } from "react-router-dom";
import { Sidebar } from "./components/Sidebar";

export default function App() {
  return (
    <div className="min-h-screen flex">
      <Sidebar />
      <main className="flex-1 p-8 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
```

- [ ] **Step 5: Replace `frontend/src/main.tsx`**

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import App from "./App";
import { Dashboard } from "./pages/Dashboard";
import { Transactions } from "./pages/Transactions";
import { Accounts } from "./pages/Accounts";
import { Holdings } from "./pages/Holdings";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: false } },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<App />}>
            <Route index element={<Dashboard />} />
            <Route path="transactions" element={<Transactions />} />
            <Route path="accounts" element={<Accounts />} />
            <Route path="holdings" element={<Holdings />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
```

- [ ] **Step 6: Create page placeholders**

Write to `frontend/src/pages/Dashboard.tsx`:

```tsx
export function Dashboard() {
  return <h2 className="text-2xl font-semibold">Dashboard</h2>;
}
```

Write to `frontend/src/pages/Transactions.tsx`:

```tsx
export function Transactions() {
  return <h2 className="text-2xl font-semibold">Transactions</h2>;
}
```

Write to `frontend/src/pages/Accounts.tsx`:

```tsx
export function Accounts() {
  return <h2 className="text-2xl font-semibold">Accounts</h2>;
}
```

Write to `frontend/src/pages/Holdings.tsx`:

```tsx
export function Holdings() {
  return <h2 className="text-2xl font-semibold">Holdings</h2>;
}
```

- [ ] **Step 7: Boot smoke test**

```bash
cd /Users/bibas/personal/finance-tracker/frontend
timeout 6 pnpm dev 2>&1 | head -20 || true
```

Expected: Vite serves cleanly on `:5173`, no compile errors.

- [ ] **Step 8: Commit**

```bash
cd /Users/bibas/personal/finance-tracker
git add frontend/src
git commit -m "feat(frontend): API client + TanStack Query + Router + sidebar (Plan 5, Task 2)"
```

---

## Task 3: Accounts page + Plaid Link Add Account flow

**Files:**
- Create: `frontend/src/components/AddAccountButton.tsx`
- Create: `frontend/src/components/Money.tsx`
- Create: `frontend/src/components/SyncButton.tsx`
- Replace: `frontend/src/pages/Accounts.tsx`

- [ ] **Step 1: `Money.tsx`**

```tsx
export function Money({ value, currency = "USD" }: { value: number | null; currency?: string | null }) {
  if (value === null || value === undefined) return <span className="text-gray-400">—</span>;
  const formatted = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency || "USD",
  }).format(value);
  return <span>{formatted}</span>;
}
```

- [ ] **Step 2: `AddAccountButton.tsx`**

```tsx
import { useEffect, useState } from "react";
import { usePlaidLink, PlaidLinkOnSuccessMetadata } from "react-plaid-link";
import { Plus } from "lucide-react";

import { useExchangePublicToken, useLinkToken } from "../api/queries";

export function AddAccountButton() {
  const [linkToken, setLinkToken] = useState<string | null>(null);
  const linkTokenMutation = useLinkToken();
  const exchangeMutation = useExchangePublicToken();

  const { open, ready } = usePlaidLink({
    token: linkToken,
    onSuccess: (publicToken: string, _metadata: PlaidLinkOnSuccessMetadata) => {
      exchangeMutation.mutate(publicToken);
      setLinkToken(null);
    },
    onExit: () => {
      setLinkToken(null);
    },
  });

  useEffect(() => {
    if (linkToken && ready) {
      open();
    }
  }, [linkToken, ready, open]);

  const handleClick = async () => {
    const result = await linkTokenMutation.mutateAsync();
    setLinkToken(result.link_token);
  };

  const busy = linkTokenMutation.isPending || exchangeMutation.isPending || (!!linkToken && !ready);

  return (
    <button
      onClick={handleClick}
      disabled={busy}
      className="inline-flex items-center gap-2 rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50"
    >
      <Plus className="h-4 w-4" />
      {busy ? "Connecting…" : "Add Account"}
    </button>
  );
}
```

- [ ] **Step 3: `SyncButton.tsx`**

```tsx
import { RefreshCw } from "lucide-react";
import clsx from "clsx";

import { useStartSync, useSyncStatus } from "../api/queries";

export function SyncButton() {
  const startSync = useStartSync();
  const status = useSyncStatus();
  const anyPending = status.data?.some((s) => s.last_sync_status === "pending");

  return (
    <button
      onClick={() => startSync.mutate()}
      disabled={startSync.isPending || anyPending}
      className="inline-flex items-center gap-2 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
    >
      <RefreshCw className={clsx("h-4 w-4", (startSync.isPending || anyPending) && "animate-spin")} />
      {startSync.isPending || anyPending ? "Syncing…" : "Sync now"}
    </button>
  );
}
```

- [ ] **Step 4: Replace `frontend/src/pages/Accounts.tsx`**

```tsx
import { useAccounts, useSyncStatus } from "../api/queries";
import { AddAccountButton } from "../components/AddAccountButton";
import { Money } from "../components/Money";
import { SyncButton } from "../components/SyncButton";

export function Accounts() {
  const { data: accounts, isLoading } = useAccounts();
  const { data: statuses } = useSyncStatus();
  const statusByItem = new Map((statuses ?? []).map((s) => [s.item_id, s]));

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-semibold">Accounts</h2>
        <div className="flex items-center gap-2">
          <SyncButton />
          <AddAccountButton />
        </div>
      </div>
      {isLoading && <p className="text-gray-500">Loading…</p>}
      {!isLoading && accounts && accounts.length === 0 && (
        <div className="rounded-lg border border-dashed border-gray-300 p-8 text-center">
          <p className="text-gray-600 mb-3">No accounts linked yet.</p>
          <AddAccountButton />
        </div>
      )}
      {accounts && accounts.length > 0 && (
        <div className="grid gap-3">
          {accounts.map((a) => {
            const status = statusByItem.get(a.item_id);
            return (
              <div
                key={a.account_id}
                className="rounded-lg border border-gray-200 bg-white p-4 flex items-center justify-between"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{a.institution_name}</span>
                    <span className="text-gray-500">·</span>
                    <span className="text-gray-700">{a.name}</span>
                    {a.mask && <span className="text-gray-400 text-sm">•••• {a.mask}</span>}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    {a.type} {a.subtype && `· ${a.subtype}`}
                    {status?.last_sync_error && (
                      <span className="ml-2 text-red-600">⚠ {status.last_sync_error}</span>
                    )}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-lg font-medium">
                    <Money value={a.current_balance} currency={a.iso_currency_code} />
                  </div>
                  {a.limit_balance != null && (
                    <div className="text-xs text-gray-500">
                      Limit: <Money value={a.limit_balance} currency={a.iso_currency_code} />
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Boot smoke**

```bash
cd /Users/bibas/personal/finance-tracker/frontend
timeout 6 pnpm dev 2>&1 | head -20 || true
```

Expected: clean compile.

- [ ] **Step 6: Commit**

```bash
cd /Users/bibas/personal/finance-tracker
git add frontend/src
git commit -m "feat(frontend): accounts page + Plaid Link Add Account + sync button (Plan 5, Task 3)"
```

---

## Task 4: Transactions page

**Files:**
- Create: `frontend/src/components/DateRangeFilter.tsx`
- Replace: `frontend/src/pages/Transactions.tsx`

- [ ] **Step 1: `DateRangeFilter.tsx`**

```tsx
export function DateRangeFilter({
  start,
  end,
  onChange,
}: {
  start: string;
  end: string;
  onChange: (start: string, end: string) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <input
        type="date"
        value={start}
        onChange={(e) => onChange(e.target.value, end)}
        className="rounded border border-gray-300 px-2 py-1 text-sm"
      />
      <span className="text-gray-500">→</span>
      <input
        type="date"
        value={end}
        onChange={(e) => onChange(start, e.target.value)}
        className="rounded border border-gray-300 px-2 py-1 text-sm"
      />
    </div>
  );
}
```

- [ ] **Step 2: Replace `frontend/src/pages/Transactions.tsx`**

```tsx
import { useState } from "react";

import { useTransactions } from "../api/queries";
import { DateRangeFilter } from "../components/DateRangeFilter";
import { Money } from "../components/Money";

const today = new Date().toISOString().slice(0, 10);
const ninetyDaysAgo = new Date(Date.now() - 90 * 86400_000).toISOString().slice(0, 10);

export function Transactions() {
  const [start, setStart] = useState(ninetyDaysAgo);
  const [end, setEnd] = useState(today);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");

  const filters = {
    start_date: start,
    end_date: end,
    merchant_name: search || undefined,
    category_primary: category || undefined,
    limit: 500,
  };
  const { data, isLoading } = useTransactions(filters);

  return (
    <div>
      <h2 className="text-2xl font-semibold mb-6">Transactions</h2>
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <DateRangeFilter start={start} end={end} onChange={(s, e) => { setStart(s); setEnd(e); }} />
        <input
          type="text"
          placeholder="Search merchant…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="rounded border border-gray-300 px-3 py-1 text-sm"
        />
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="rounded border border-gray-300 px-2 py-1 text-sm"
        >
          <option value="">All categories</option>
          <option value="FOOD_AND_DRINK">Food & Drink</option>
          <option value="TRANSPORTATION">Transportation</option>
          <option value="GENERAL_MERCHANDISE">General Merchandise</option>
          <option value="INCOME">Income</option>
          <option value="ENTERTAINMENT">Entertainment</option>
          <option value="RENT_AND_UTILITIES">Rent & Utilities</option>
          <option value="MEDICAL">Medical</option>
          <option value="TRAVEL">Travel</option>
          <option value="GENERAL_SERVICES">General Services</option>
          <option value="LOAN_PAYMENTS">Loan Payments</option>
          <option value="TRANSFER_IN">Transfer In</option>
          <option value="TRANSFER_OUT">Transfer Out</option>
          <option value="BANK_FEES">Bank Fees</option>
        </select>
      </div>
      {isLoading && <p className="text-gray-500">Loading…</p>}
      {data && (
        <div className="rounded-lg border border-gray-200 bg-white overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-4 py-2">Date</th>
                <th className="px-4 py-2">Merchant</th>
                <th className="px-4 py-2">Category</th>
                <th className="px-4 py-2 text-right">Amount</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {data.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-6 text-center text-gray-500">
                    No transactions in this range.
                  </td>
                </tr>
              )}
              {data.map((t) => (
                <tr key={t.transaction_id}>
                  <td className="px-4 py-2 text-gray-600">{t.date}</td>
                  <td className="px-4 py-2">
                    <div className="font-medium">{t.merchant_name || t.name}</div>
                    {t.pending && <div className="text-xs text-amber-600">Pending</div>}
                  </td>
                  <td className="px-4 py-2 text-gray-500 text-xs">
                    {t.category_primary || "—"}
                  </td>
                  <td className="px-4 py-2 text-right font-medium">
                    <Money value={t.amount} currency={t.iso_currency_code} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Boot smoke + commit**

```bash
cd /Users/bibas/personal/finance-tracker/frontend
timeout 6 pnpm dev 2>&1 | head -20 || true
cd /Users/bibas/personal/finance-tracker
git add frontend/src
git commit -m "feat(frontend): transactions page with date/category/merchant filters (Plan 5, Task 4)"
```

---

## Task 5: Dashboard + Holdings pages

**Files:**
- Replace: `frontend/src/pages/Dashboard.tsx`
- Replace: `frontend/src/pages/Holdings.tsx`

- [ ] **Step 1: `Dashboard.tsx`**

```tsx
import { useCategorySpend, useNetWorth } from "../api/queries";
import { Money } from "../components/Money";

const today = new Date().toISOString().slice(0, 10);
const thirtyDaysAgo = new Date(Date.now() - 30 * 86400_000).toISOString().slice(0, 10);

export function Dashboard() {
  const { data: nw, isLoading: nwLoading } = useNetWorth();
  const { data: spend, isLoading: spendLoading } = useCategorySpend(thirtyDaysAgo, today);

  const max = (spend ?? []).reduce((m, r) => Math.max(m, r.total), 0);

  return (
    <div className="grid gap-6">
      <h2 className="text-2xl font-semibold">Dashboard</h2>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card label="Net worth" loading={nwLoading}>
          <div className="text-3xl font-semibold">
            <Money value={nw?.total ?? null} />
          </div>
        </Card>
        <Card label="Cash" loading={nwLoading}>
          <div className="text-2xl">
            <Money value={nw?.depository ?? null} />
          </div>
        </Card>
        <Card label="Investments" loading={nwLoading}>
          <div className="text-2xl">
            <Money value={nw?.investment ?? null} />
          </div>
        </Card>
      </div>

      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <h3 className="font-medium mb-3">Spending by category — last 30 days</h3>
        {spendLoading && <p className="text-gray-500 text-sm">Loading…</p>}
        {spend && spend.length === 0 && <p className="text-gray-500 text-sm">No spending recorded.</p>}
        {spend && spend.length > 0 && (
          <div className="grid gap-2">
            {spend.map((row) => (
              <div key={row.category_primary} className="flex items-center gap-3">
                <div className="w-44 text-sm text-gray-600">{row.category_primary}</div>
                <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gray-900"
                    style={{ width: `${(row.total / max) * 100}%` }}
                  />
                </div>
                <div className="w-24 text-right text-sm font-medium">
                  <Money value={row.total} />
                </div>
                <div className="w-12 text-right text-xs text-gray-500">{row.count}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function Card({ label, loading, children }: { label: string; loading?: boolean; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="text-xs uppercase tracking-wide text-gray-500 mb-2">{label}</div>
      {loading ? <div className="h-6 bg-gray-100 rounded w-24 animate-pulse" /> : children}
    </div>
  );
}
```

- [ ] **Step 2: `Holdings.tsx`**

```tsx
import { useHoldings } from "../api/queries";
import { Money } from "../components/Money";

export function Holdings() {
  const { data, isLoading } = useHoldings();
  return (
    <div>
      <h2 className="text-2xl font-semibold mb-6">Holdings</h2>
      {isLoading && <p className="text-gray-500">Loading…</p>}
      {data && data.length === 0 && <p className="text-gray-500">No holdings — link an investment account.</p>}
      {data && data.length > 0 && (
        <div className="rounded-lg border border-gray-200 bg-white overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-4 py-2">Account</th>
                <th className="px-4 py-2">Ticker</th>
                <th className="px-4 py-2">Name</th>
                <th className="px-4 py-2 text-right">Quantity</th>
                <th className="px-4 py-2 text-right">Price</th>
                <th className="px-4 py-2 text-right">Value</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {data.map((h) => (
                <tr key={`${h.account_id}-${h.security_id}`}>
                  <td className="px-4 py-2 text-gray-600">{h.account_name}</td>
                  <td className="px-4 py-2 font-medium">{h.ticker_symbol || "—"}</td>
                  <td className="px-4 py-2">{h.security_name}</td>
                  <td className="px-4 py-2 text-right">{h.quantity}</td>
                  <td className="px-4 py-2 text-right">
                    <Money value={h.institution_price} currency={h.iso_currency_code} />
                  </td>
                  <td className="px-4 py-2 text-right font-medium">
                    <Money value={h.institution_value} currency={h.iso_currency_code} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Boot smoke + commit**

```bash
cd /Users/bibas/personal/finance-tracker/frontend
timeout 6 pnpm dev 2>&1 | head -20 || true
cd /Users/bibas/personal/finance-tracker
git add frontend/src
git commit -m "feat(frontend): dashboard + holdings pages (Plan 5, Task 5)"
```

---

## Task 6: Combined dev script — uvicorn + Vite together

**Files:**
- Create: `scripts/run-dev.py`
- Modify: `Makefile`

- [ ] **Step 1: Write `scripts/run-dev.py`**

```python
#!/usr/bin/env python3
"""Supervisor that runs uvicorn + Vite together.

Ctrl-C kills both. Output from each process is prefixed.
"""
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VENV = REPO_ROOT / ".venv"
FRONTEND = REPO_ROOT / "frontend"


def stream(proc: subprocess.Popen, prefix: str, color: str):
    for line in iter(proc.stdout.readline, b""):
        sys.stdout.write(f"\033[{color}m[{prefix}]\033[0m {line.decode(errors='replace')}")
        sys.stdout.flush()


def main():
    if not (FRONTEND / "node_modules").exists():
        print("frontend/node_modules missing — run `cd frontend && pnpm install` (or `npm install`) first.")
        sys.exit(1)

    backend = subprocess.Popen(
        [str(VENV / "bin" / "uvicorn"), "api.main:app",
         "--host", "127.0.0.1", "--port", "8000", "--reload"],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    npm_or_pnpm = "pnpm" if (FRONTEND / "pnpm-lock.yaml").exists() else "npm"
    frontend = subprocess.Popen(
        [npm_or_pnpm, "run", "dev"],
        cwd=FRONTEND,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    threading.Thread(target=stream, args=(backend, "api", "36"), daemon=True).start()
    threading.Thread(target=stream, args=(frontend, "ui", "32"), daemon=True).start()

    def shutdown(signum, frame):
        for p in (backend, frontend):
            try:
                p.send_signal(signal.SIGTERM)
            except ProcessLookupError:
                pass
        time.sleep(1)
        for p in (backend, frontend):
            if p.poll() is None:
                p.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Wait for either to exit; if one dies, kill the other.
    while True:
        if backend.poll() is not None:
            print(f"[api] exited with {backend.returncode}; stopping ui")
            shutdown(None, None)
        if frontend.poll() is not None:
            print(f"[ui] exited with {frontend.returncode}; stopping api")
            shutdown(None, None)
        time.sleep(0.5)


if __name__ == "__main__":
    main()
```

```bash
chmod +x /Users/bibas/personal/finance-tracker/scripts/run-dev.py
```

- [ ] **Step 2: Update `Makefile`**

Replace the `dev` target in `Makefile`:

```makefile
dev:
	@echo "Starting Finance Tracker — backend on :8000, frontend on :5173 (Ctrl-C to stop)"
	$(PYTHON) scripts/run-dev.py
```

The full `Makefile` should now be:

```makefile
.PHONY: dev test migrate clean help

VENV := .venv
PYTHON := $(VENV)/bin/python
UVICORN := $(VENV)/bin/uvicorn
ALEMBIC := $(VENV)/bin/alembic
PYTEST := $(VENV)/bin/pytest

help:
	@echo "Targets:"
	@echo "  make dev      — run uvicorn (api) + Vite (ui) together"
	@echo "  make test     — run the full test suite"
	@echo "  make migrate  — run alembic upgrade head"
	@echo "  make clean    — remove .pyc files and pytest cache"

dev:
	@echo "Starting Finance Tracker — backend on :8000, frontend on :5173 (Ctrl-C to stop)"
	$(PYTHON) scripts/run-dev.py

test:
	$(PYTEST) -v

migrate:
	$(ALEMBIC) upgrade head

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	rm -rf .pytest_cache htmlcov .coverage
```

- [ ] **Step 3: Smoke `make help`**

```bash
make help
```

Expected: prints the help text including the new `dev` description.

**Do NOT** run `make dev` from the agent — that starts long-running servers that won't exit.

- [ ] **Step 4: Commit**

```bash
git add scripts/run-dev.py Makefile
git commit -m "feat(launcher): run-dev.py supervisor — uvicorn + vite together (Plan 5, Task 6)"
```

---

## Plan 5 Verification

- Backend tests still pass: `make test 2>&1 | tail -3` → 106 passed + 1 skipped.
- Frontend builds: `cd frontend && pnpm build` → succeeds without TS errors.
- Manual smoke (user-driven):
  1. `make dev` → boots uvicorn + Vite.
  2. Open `http://localhost:5173` → shows the Finance Tracker shell with sidebar.
  3. Click **Add Account** → Plaid Link iframe opens.
  4. Complete the link in Plaid Sandbox → returns to UI; account appears.
  5. Click **Sync now** → spinner; transactions populate.

---

## Hand-off to Plan 6

Plan 6 (MCP server) will:
- Add `mcp/` package — stdio-based MCP server using the official MCP Python SDK.
- 5 tools mirroring `core.queries.*` — read-only.
- Schema-version check at startup (refuses if Alembic head doesn't match DB).
- Generate the exact JSON snippet to add to `~/Library/Application Support/Claude/claude_desktop_config.json` (user pastes manually).
