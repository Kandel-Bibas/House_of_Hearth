import { useCategorySpend, useNetWorth } from "../api/queries";
import { Money } from "../components/Money";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";

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
        <Card size="sm">
          <CardHeader>
            <CardTitle className="text-xs uppercase tracking-wide text-muted-foreground">
              Net worth
            </CardTitle>
          </CardHeader>
          <CardContent>
            {nwLoading ? (
              <div className="h-6 bg-muted rounded w-24 animate-pulse" />
            ) : (
              <div className="text-3xl font-semibold">
                <Money value={nw?.total ?? null} />
              </div>
            )}
          </CardContent>
        </Card>
        <Card size="sm">
          <CardHeader>
            <CardTitle className="text-xs uppercase tracking-wide text-muted-foreground">
              Cash
            </CardTitle>
          </CardHeader>
          <CardContent>
            {nwLoading ? (
              <div className="h-6 bg-muted rounded w-24 animate-pulse" />
            ) : (
              <div className="text-2xl">
                <Money value={nw?.depository ?? null} />
              </div>
            )}
          </CardContent>
        </Card>
        <Card size="sm">
          <CardHeader>
            <CardTitle className="text-xs uppercase tracking-wide text-muted-foreground">
              Investments
            </CardTitle>
          </CardHeader>
          <CardContent>
            {nwLoading ? (
              <div className="h-6 bg-muted rounded w-24 animate-pulse" />
            ) : (
              <div className="text-2xl">
                <Money value={nw?.investment ?? null} />
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <Card size="sm">
        <CardHeader>
          <CardTitle>Spending by category — last 30 days</CardTitle>
        </CardHeader>
        <CardContent>
          {spendLoading && <p className="text-muted-foreground text-sm">Loading…</p>}
          {spend && spend.length === 0 && (
            <p className="text-muted-foreground text-sm">No spending recorded.</p>
          )}
          {spend && spend.length > 0 && (
            <div className="grid gap-2">
              {spend.map((row) => (
                <div key={row.category_primary} className="flex items-center gap-3">
                  <div className="w-44 text-sm text-muted-foreground">{row.category_primary}</div>
                  <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                    <div
                      className="h-full bg-foreground"
                      style={{ width: `${(row.total / max) * 100}%` }}
                    />
                  </div>
                  <div className="w-24 text-right text-sm font-medium">
                    <Money value={row.total} />
                  </div>
                  <div className="w-12 text-right text-xs text-muted-foreground">{row.count}</div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
