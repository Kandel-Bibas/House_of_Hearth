import { useState } from "react";

import { useTransactions } from "../api/queries";
import { DateRangeFilter } from "../components/DateRangeFilter";
import { Money } from "../components/Money";
import { Input } from "../components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../components/ui/table";
import { Card } from "../components/ui/card";

const today = new Date().toISOString().slice(0, 10);
const ninetyDaysAgo = new Date(Date.now() - 90 * 86400_000).toISOString().slice(0, 10);

const ALL_CATEGORIES = "__all__";

const CATEGORIES: { value: string; label: string }[] = [
  { value: "FOOD_AND_DRINK", label: "Food & Drink" },
  { value: "TRANSPORTATION", label: "Transportation" },
  { value: "GENERAL_MERCHANDISE", label: "General Merchandise" },
  { value: "INCOME", label: "Income" },
  { value: "ENTERTAINMENT", label: "Entertainment" },
  { value: "RENT_AND_UTILITIES", label: "Rent & Utilities" },
  { value: "MEDICAL", label: "Medical" },
  { value: "TRAVEL", label: "Travel" },
  { value: "GENERAL_SERVICES", label: "General Services" },
  { value: "LOAN_PAYMENTS", label: "Loan Payments" },
  { value: "TRANSFER_IN", label: "Transfer In" },
  { value: "TRANSFER_OUT", label: "Transfer Out" },
  { value: "BANK_FEES", label: "Bank Fees" },
];

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
        <Input
          type="text"
          placeholder="Search merchant…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-auto"
        />
        <Select
          value={category === "" ? ALL_CATEGORIES : category}
          onValueChange={(v) => setCategory(v === ALL_CATEGORIES ? "" : v)}
        >
          <SelectTrigger className="w-[200px]">
            <SelectValue placeholder="All categories" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL_CATEGORIES}>All categories</SelectItem>
            {CATEGORIES.map((c) => (
              <SelectItem key={c.value} value={c.value}>
                {c.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {isLoading && <p className="text-muted-foreground">Loading…</p>}
      {data && (
        <Card size="sm" className="py-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead>Merchant</TableHead>
                <TableHead>Account</TableHead>
                <TableHead>Category</TableHead>
                <TableHead className="text-right">Amount</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-muted-foreground py-6">
                    No transactions in this range.
                  </TableCell>
                </TableRow>
              )}
              {data.map((t) => (
                <TableRow key={t.transaction_id}>
                  <TableCell className="text-muted-foreground">{t.date}</TableCell>
                  <TableCell>
                    <div className="font-medium">{t.merchant_name || t.name}</div>
                    {t.pending && <div className="text-xs text-amber-500">Pending</div>}
                  </TableCell>
                  <TableCell>
                    <div>{t.institution_name}</div>
                    <div className="text-xs text-muted-foreground">{t.account_name}</div>
                  </TableCell>
                  <TableCell className="text-muted-foreground text-xs">
                    {t.category_primary || "—"}
                  </TableCell>
                  <TableCell className="text-right font-medium">
                    <Money value={t.amount} currency={t.iso_currency_code} />
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
