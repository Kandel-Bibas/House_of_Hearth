export function Money({ value, currency = "USD" }: { value: number | null; currency?: string | null }) {
  if (value === null || value === undefined) return <span className="text-gray-400">—</span>;
  const formatted = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency || "USD",
  }).format(value);
  return <span>{formatted}</span>;
}
