import { useState, useCallback } from "react";
import usePolling from "./hooks/usePolling";
import {
  fetchSummary,
  fetchOpenPositions,
  fetchClosedPositions,
  fetchPnlTimeline,
} from "./api";
import ModeToggle from "./components/ModeToggle";
import SummaryCards from "./components/SummaryCards";
import OpenPositions from "./components/OpenPositions";
import TradeHistory from "./components/TradeHistory";
import PnlChart from "./components/PnlChart";

export default function App() {
  const [mode, setMode] = useState("paper");

  const summary = usePolling(useCallback(() => fetchSummary(mode), [mode]));
  const openPos = usePolling(
    useCallback(() => fetchOpenPositions(mode), [mode])
  );
  const closedPos = usePolling(
    useCallback(() => fetchClosedPositions(mode), [mode])
  );
  const timeline = usePolling(
    useCallback(() => fetchPnlTimeline(mode), [mode])
  );

  const anyLoading =
    summary.loading || openPos.loading || closedPos.loading || timeline.loading;
  const anyError =
    summary.error || openPos.error || closedPos.error || timeline.error;

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">
          Kalshi Weather Dashboard
        </h1>
        <ModeToggle mode={mode} setMode={setMode} />
      </div>

      {anyError && (
        <div className="mb-4 rounded-lg border border-red-800 bg-red-950 p-3 text-sm text-red-400">
          API error: {anyError} — is the backend running on :8000?
        </div>
      )}

      {anyLoading && !summary.data ? (
        <p className="text-gray-500">Loading...</p>
      ) : (
        <div className="space-y-6">
          <SummaryCards data={summary.data} />
          <PnlChart data={timeline.data} />
          <div className="grid gap-6 lg:grid-cols-2">
            <OpenPositions data={openPos.data} />
            <TradeHistory data={closedPos.data} />
          </div>
        </div>
      )}
    </div>
  );
}
