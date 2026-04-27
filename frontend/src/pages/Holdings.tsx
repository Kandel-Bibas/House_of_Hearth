import { useHoldings } from "../api/queries";
import { Money } from "../components/Money";
import { Card } from "../components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../components/ui/table";

export function Holdings() {
  const { data, isLoading } = useHoldings();
  return (
    <div>
      <h2 className="text-2xl font-semibold mb-6">Holdings</h2>
      {isLoading && <p className="text-muted-foreground">Loading…</p>}
      {data && data.length === 0 && (
        <p className="text-muted-foreground">No holdings — link an investment account.</p>
      )}
      {data && data.length > 0 && (
        <Card size="sm" className="py-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Account</TableHead>
                <TableHead>Ticker</TableHead>
                <TableHead>Name</TableHead>
                <TableHead className="text-right">Quantity</TableHead>
                <TableHead className="text-right">Price</TableHead>
                <TableHead className="text-right">Value</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((h) => (
                <TableRow key={`${h.account_id}-${h.security_id}`}>
                  <TableCell className="text-muted-foreground">{h.account_name}</TableCell>
                  <TableCell className="font-medium">{h.ticker_symbol || "—"}</TableCell>
                  <TableCell>{h.security_name}</TableCell>
                  <TableCell className="text-right">{h.quantity}</TableCell>
                  <TableCell className="text-right">
                    <Money value={h.institution_price} currency={h.iso_currency_code} />
                  </TableCell>
                  <TableCell className="text-right font-medium">
                    <Money value={h.institution_value} currency={h.iso_currency_code} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
    </div>
  );
}
