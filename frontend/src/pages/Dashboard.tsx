import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";
import { useCategorySpend, useNetWorth } from "../api/queries";
import { Money } from "../components/Money";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "../components/ui/chart";

const today = new Date().toISOString().slice(0, 10);
const thirtyDaysAgo = new Date(Date.now() - 30 * 86400_000).toISOString().slice(0, 10);

const chartConfig = {
  total: {
    label: "Spend",
    color: "var(--chart-1)",
  },
} satisfies ChartConfig;

export function Dashboard() {
  const { data: nw, isLoading: nwLoading } = useNetWorth();
  const { data: spend, isLoading: spendLoading } = useCategorySpend(thirtyDaysAgo, today);

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
            <ChartContainer config={chartConfig} className="aspect-auto h-[400px] w-full">
              <BarChart
                accessibilityLayer
                data={spend}
                layout="vertical"
                margin={{ left: 16, right: 16, top: 8, bottom: 8 }}
              >
                <CartesianGrid horizontal={false} strokeDasharray="3 3" />
                <XAxis
                  type="number"
                  tickFormatter={(v) => `$${Number(v).toLocaleString()}`}
                />
                <YAxis
                  type="category"
                  dataKey="category_primary"
                  width={140}
                  tick={{ fontSize: 12 }}
                  tickLine={false}
                  axisLine={false}
                />
                <ChartTooltip
                  cursor={false}
                  content={
                    <ChartTooltipContent
                      formatter={(value) => `$${Number(value).toLocaleString()}`}
                    />
                  }
                />
                <Bar dataKey="total" fill="var(--color-total)" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ChartContainer>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
