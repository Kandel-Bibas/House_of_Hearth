import { useHoldings } from "../api/queries";
import { Money } from "../components/Money";

export function Holdings() {
  const { data, isLoading } = useHoldings();
  return (
    <div>
      <h2 className="text-2xl font-semibold mb-6">Holdings</h2>
      {isLoading && <p className="text-gray-500">Loading…</p>}
      {data && data.length === 0 && <p className="text-gray-500">No holdings — link an investment account.</p>}
      {data && data.length > 0 && (
        <div className="rounded-lg border border-gray-200 bg-white overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-4 py-2">Account</th>
                <th className="px-4 py-2">Ticker</th>
                <th className="px-4 py-2">Name</th>
                <th className="px-4 py-2 text-right">Quantity</th>
                <th className="px-4 py-2 text-right">Price</th>
                <th className="px-4 py-2 text-right">Value</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {data.map((h) => (
                <tr key={`${h.account_id}-${h.security_id}`}>
                  <td className="px-4 py-2 text-gray-600">{h.account_name}</td>
                  <td className="px-4 py-2 font-medium">{h.ticker_symbol || "—"}</td>
                  <td className="px-4 py-2">{h.security_name}</td>
                  <td className="px-4 py-2 text-right">{h.quantity}</td>
                  <td className="px-4 py-2 text-right">
                    <Money value={h.institution_price} currency={h.iso_currency_code} />
                  </td>
                  <td className="px-4 py-2 text-right font-medium">
                    <Money value={h.institution_value} currency={h.iso_currency_code} />
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
