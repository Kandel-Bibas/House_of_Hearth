import { useAccounts, useSyncStatus } from "../api/queries";
import { AddAccountButton } from "../components/AddAccountButton";
import { Money } from "../components/Money";
import { SyncButton } from "../components/SyncButton";
import { Card, CardContent, CardHeader } from "../components/ui/card";

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
      {isLoading && <p className="text-muted-foreground">Loading…</p>}
      {!isLoading && accounts && accounts.length === 0 && (
        <Card>
          <CardContent className="p-8 text-center">
            <p className="text-muted-foreground mb-3">No accounts linked yet.</p>
            <AddAccountButton />
          </CardContent>
        </Card>
      )}
      {accounts && accounts.length > 0 && (
        <div className="grid gap-3">
          {accounts.map((a) => {
            const status = statusByItem.get(a.item_id);
            return (
              <Card key={a.account_id} size="sm">
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-foreground">{a.institution_name}</span>
                        <span className="text-muted-foreground">·</span>
                        <span className="text-foreground">{a.name}</span>
                        {a.mask && (
                          <span className="text-muted-foreground text-sm">•••• {a.mask}</span>
                        )}
                      </div>
                      <div className="text-xs text-muted-foreground mt-1">
                        {a.type} {a.subtype && `· ${a.subtype}`}
                        {status?.last_sync_error && (
                          <span className="ml-2 text-destructive">⚠ {status.last_sync_error}</span>
                        )}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-lg font-medium">
                        <Money value={a.current_balance} currency={a.iso_currency_code} />
                      </div>
                      {a.limit_balance != null && (
                        <div className="text-xs text-muted-foreground">
                          Limit: <Money value={a.limit_balance} currency={a.iso_currency_code} />
                        </div>
                      )}
                    </div>
                  </div>
                </CardHeader>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
