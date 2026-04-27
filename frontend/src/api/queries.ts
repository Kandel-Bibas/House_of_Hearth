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
