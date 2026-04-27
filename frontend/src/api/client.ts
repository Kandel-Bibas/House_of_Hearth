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
