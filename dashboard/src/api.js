const BASE = "/api";

async function fetchJson(path, mode) {
  const res = await fetch(`${BASE}${path}?mode=${mode}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export const fetchSummary = (mode) => fetchJson("/summary", mode);
export const fetchOpenPositions = (mode) => fetchJson("/positions/open", mode);
export const fetchClosedPositions = (mode) => fetchJson("/positions/closed", mode);
export const fetchPnlTimeline = (mode) => fetchJson("/pnl-timeline", mode);
