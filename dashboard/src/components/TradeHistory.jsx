function fmt(cents) {
  return (cents / 100).toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
  });
}

function fmtDate(iso) {
  if (!iso) return "-";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function TradeHistory({ data }) {
  if (!data) return null;

  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
      <h2 className="mb-3 text-lg font-semibold text-gray-200">
        Trade History
      </h2>
      {data.length === 0 ? (
        <p className="text-sm text-gray-500">No closed trades</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 text-left text-gray-400">
                <th className="pb-2 pr-4">Ticker</th>
                <th className="pb-2 pr-4">Side</th>
                <th className="pb-2 pr-4 text-right">Qty</th>
                <th className="pb-2 pr-4 text-right">Entry</th>
                <th className="pb-2 pr-4 text-right">Exit</th>
                <th className="pb-2 pr-4 text-right">P&L</th>
                <th className="pb-2 text-right">Closed</th>
              </tr>
            </thead>
            <tbody>
              {[...data].reverse().map((p, i) => (
                <tr key={i} className="border-b border-gray-800/50">
                  <td className="py-2 pr-4 font-mono">{p.ticker}</td>
                  <td className="py-2 pr-4">
                    <span
                      className={`font-semibold ${
                        p.side === "yes" ? "text-green-400" : "text-red-400"
                      }`}
                    >
                      {p.side.toUpperCase()}
                    </span>
                  </td>
                  <td className="py-2 pr-4 text-right font-mono">
                    {p.contracts}
                  </td>
                  <td className="py-2 pr-4 text-right font-mono">
                    {p.avg_price_cents}c
                  </td>
                  <td className="py-2 pr-4 text-right font-mono">
                    {p.close_price_cents}c
                  </td>
                  <td
                    className={`py-2 pr-4 text-right font-mono font-semibold ${
                      (p.pnl_cents || 0) >= 0
                        ? "text-green-500"
                        : "text-red-500"
                    }`}
                  >
                    {fmt(p.pnl_cents || 0)}
                  </td>
                  <td className="py-2 text-right text-gray-400">
                    {fmtDate(p.closed_at)}
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
