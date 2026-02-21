function fmt(cents) {
  return (cents / 100).toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
  });
}

export default function OpenPositions({ data }) {
  if (!data) return null;

  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
      <h2 className="mb-3 text-lg font-semibold text-gray-200">
        Open Positions
      </h2>
      {data.length === 0 ? (
        <p className="text-sm text-gray-500">No open positions</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 text-left text-gray-400">
                <th className="pb-2 pr-4">Ticker</th>
                <th className="pb-2 pr-4">Side</th>
                <th className="pb-2 pr-4 text-right">Qty</th>
                <th className="pb-2 pr-4 text-right">Price</th>
                <th className="pb-2 text-right">Cost</th>
              </tr>
            </thead>
            <tbody>
              {data.map((p, i) => (
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
                  <td className="py-2 text-right font-mono">
                    {fmt(p.cost_cents)}
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
