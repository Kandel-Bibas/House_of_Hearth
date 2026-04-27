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
