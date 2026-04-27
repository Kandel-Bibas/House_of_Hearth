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
