import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

import { useAccounts, useTransactions } from "../api/queries";
import { DateRangeFilter } from "../components/DateRangeFilter";
import { Money } from "../components/Money";
import { Avatar, AvatarFallback, AvatarImage } from "../components/ui/avatar";
import { Card } from "../components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../components/ui/table";

const today = new Date().toISOString().slice(0, 10);
const ninetyDaysAgo = new Date(Date.now() - 90 * 86400_000).toISOString().slice(0, 10);

export function AccountDetail() {
  const { accountId } = useParams<{ accountId: string }>();
  const [start, setStart] = useState(ninetyDaysAgo);
  const [end, setEnd] = useState(today);

  const { data: accounts, isLoading: accountsLoading } = useAccounts();
  const account = accounts?.find((a) => a.account_id === accountId);

  const { data: transactions, isLoading: txLoading } = useTransactions({
    account_id: accountId,
    start_date: start,
    end_date: end,
    limit: 500,
  });

  return (
    <div>
      <Link
        to="/accounts"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-4"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to accounts
      </Link>

      {accountsLoading && <p className="text-muted-foreground">Loading…</p>}

      {!accountsLoading && !account && (
        <Card size="sm">
          <div className="p-6 text-center text-muted-foreground">
            Account not found.
          </div>
        </Card>
      )}

      {account && (
        <>
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <Avatar size="lg">
                {account.institution_logo && (
                  <AvatarImage
                    src={`data:image/png;base64,${account.institution_logo}`}
                    alt={account.institution_name}
                  />
                )}
                <AvatarFallback>
                  {account.institution_name.charAt(0).toUpperCase()}
                </AvatarFallback>
              </Avatar>
              <div>
                <h2 className="text-2xl font-semibold leading-tight">
                  {account.name}
                </h2>
                <div className="text-sm text-muted-foreground">
                  {account.institution_name}
                  {account.mask && <span className="ml-2">•••• {account.mask}</span>}
                  <span className="ml-2">
                    {account.type}
                    {account.subtype && ` · ${account.subtype}`}
                  </span>
                </div>
              </div>
            </div>
            <div className="text-right">
              <div className="text-2xl font-medium">
                <Money value={account.current_balance} currency={account.iso_currency_code} />
              </div>
              {account.limit_balance != null && (
                <div className="text-xs text-muted-foreground">
                  Limit: <Money value={account.limit_balance} currency={account.iso_currency_code} />
                </div>
              )}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3 mb-4">
            <DateRangeFilter
              start={start}
              end={end}
              onChange={(s, e) => {
                setStart(s);
                setEnd(e);
              }}
            />
          </div>

          {txLoading && <p className="text-muted-foreground">Loading…</p>}
          {transactions && (
            <Card size="sm" className="py-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Date</TableHead>
                    <TableHead>Merchant</TableHead>
                    <TableHead>Category</TableHead>
                    <TableHead className="text-right">Amount</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {transactions.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={4} className="text-center text-muted-foreground py-6">
                        No transactions in this range.
                      </TableCell>
                    </TableRow>
                  )}
                  {transactions.map((t) => (
                    <TableRow key={t.transaction_id}>
                      <TableCell className="text-muted-foreground">{t.date}</TableCell>
                      <TableCell>
                        <div className="font-medium">{t.merchant_name || t.name}</div>
                        {t.pending && <div className="text-xs text-amber-500">Pending</div>}
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
        </>
      )}
    </div>
  );
}
