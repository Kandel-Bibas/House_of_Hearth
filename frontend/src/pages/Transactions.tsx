import { useState } from "react";

import { useTransactions } from "../api/queries";
import { DateRangeFilter } from "../components/DateRangeFilter";
import { Money } from "../components/Money";

const today = new Date().toISOString().slice(0, 10);
const ninetyDaysAgo = new Date(Date.now() - 90 * 86400_000).toISOString().slice(0, 10);

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
        <input
          type="text"
          placeholder="Search merchant…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="rounded border border-gray-300 px-3 py-1 text-sm"
        />
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="rounded border border-gray-300 px-2 py-1 text-sm"
        >
          <option value="">All categories</option>
          <option value="FOOD_AND_DRINK">Food & Drink</option>
          <option value="TRANSPORTATION">Transportation</option>
          <option value="GENERAL_MERCHANDISE">General Merchandise</option>
          <option value="INCOME">Income</option>
          <option value="ENTERTAINMENT">Entertainment</option>
          <option value="RENT_AND_UTILITIES">Rent & Utilities</option>
          <option value="MEDICAL">Medical</option>
          <option value="TRAVEL">Travel</option>
          <option value="GENERAL_SERVICES">General Services</option>
          <option value="LOAN_PAYMENTS">Loan Payments</option>
          <option value="TRANSFER_IN">Transfer In</option>
          <option value="TRANSFER_OUT">Transfer Out</option>
          <option value="BANK_FEES">Bank Fees</option>
        </select>
      </div>
      {isLoading && <p className="text-gray-500">Loading…</p>}
      {data && (
        <div className="rounded-lg border border-gray-200 bg-white overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-4 py-2">Date</th>
                <th className="px-4 py-2">Merchant</th>
                <th className="px-4 py-2">Category</th>
                <th className="px-4 py-2 text-right">Amount</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {data.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-6 text-center text-gray-500">
                    No transactions in this range.
                  </td>
                </tr>
              )}
              {data.map((t) => (
                <tr key={t.transaction_id}>
                  <td className="px-4 py-2 text-gray-600">{t.date}</td>
                  <td className="px-4 py-2">
                    <div className="font-medium">{t.merchant_name || t.name}</div>
                    {t.pending && <div className="text-xs text-amber-600">Pending</div>}
                  </td>
                  <td className="px-4 py-2 text-gray-500 text-xs">
                    {t.category_primary || "—"}
                  </td>
                  <td className="px-4 py-2 text-right font-medium">
                    <Money value={t.amount} currency={t.iso_currency_code} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
