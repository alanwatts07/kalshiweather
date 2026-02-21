function fmt(cents) {
  const dollars = cents / 100;
  return dollars.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
  });
}

function Card({ label, value, colored }) {
  const colorClass = colored
    ? value >= 0
      ? "text-green-500"
      : "text-red-500"
    : "text-white";

  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
      <p className="text-sm text-gray-400">{label}</p>
      <p className={`mt-1 text-2xl font-mono font-semibold ${colorClass}`}>
        {fmt(value)}
      </p>
    </div>
  );
}

export default function SummaryCards({ data }) {
  if (!data) return null;

  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <Card label="Cash Balance" value={data.cash_balance_cents} />
      <Card label="Equity" value={data.equity_cents} />
      <Card label="Total P&L" value={data.total_pnl_cents} colored />
      <Card label="Realized P&L" value={data.realized_pnl_cents} colored />
    </div>
  );
}
