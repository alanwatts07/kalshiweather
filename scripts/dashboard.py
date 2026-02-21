#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "fastapi>=0.115.0",
#     "uvicorn>=0.34.0",
# ]
# ///
"""
Dashboard API for Kalshi weather trading positions.

Read-only FastAPI backend that serves position data from the local JSON store.

Usage:
    uv run scripts/dashboard.py          # http://localhost:8000
"""

from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

# Add parent dir to path so we can import lib/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.positions import PositionStore

app = FastAPI(title="Kalshi Weather Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _load_store() -> PositionStore:
    return PositionStore.load()


def _filter_positions(store: PositionStore, mode: str):
    return [p for p in store.positions if p.mode == mode]


@app.get("/api/summary")
def summary(mode: str = Query("paper", pattern="^(paper|live)$")):
    store = _load_store()
    positions = _filter_positions(store, mode)
    open_pos = [p for p in positions if p.is_open]
    closed_pos = [p for p in positions if not p.is_open]

    if mode == "paper":
        cash = store.paper_balance_cents
        equity = store.paper_equity_cents
        total_pnl = store.paper_pnl_cents
        realized = store.realized_pnl_cents
    else:
        # Live mode: compute from positions only (no local cash tracking)
        realized = sum(p.pnl_cents or 0 for p in closed_pos)
        open_cost = sum(p.cost_cents for p in open_pos)
        cash = 0
        equity = open_cost
        total_pnl = realized

    return {
        "cash_balance_cents": cash,
        "equity_cents": equity,
        "total_pnl_cents": total_pnl,
        "realized_pnl_cents": realized,
        "open_count": len(open_pos),
        "closed_count": len(closed_pos),
    }


@app.get("/api/positions/open")
def open_positions(mode: str = Query("paper", pattern="^(paper|live)$")):
    store = _load_store()
    positions = _filter_positions(store, mode)
    return [
        {**asdict(p), "cost_cents": p.cost_cents}
        for p in positions
        if p.is_open
    ]


@app.get("/api/positions/closed")
def closed_positions(mode: str = Query("paper", pattern="^(paper|live)$")):
    store = _load_store()
    positions = _filter_positions(store, mode)
    return [
        {**asdict(p), "pnl_cents": p.pnl_cents}
        for p in positions
        if not p.is_open
    ]


@app.get("/api/pnl-timeline")
def pnl_timeline(mode: str = Query("paper", pattern="^(paper|live)$")):
    store = _load_store()
    positions = _filter_positions(store, mode)
    closed = sorted(
        [p for p in positions if not p.is_open and p.closed_at],
        key=lambda p: p.closed_at,
    )

    if not closed:
        # Find earliest open position for start, or return empty
        open_pos = [p for p in positions if p.is_open]
        if open_pos:
            earliest = min(p.opened_at for p in open_pos)
            return [
                {"timestamp": earliest, "cumulative_pnl_cents": 0},
            ]
        return []

    # Build timeline: start at earliest opened_at with P&L=0
    all_opened = [p.opened_at for p in positions if p.opened_at]
    earliest = min(all_opened) if all_opened else closed[0].closed_at

    points = [{"timestamp": earliest, "cumulative_pnl_cents": 0}]
    running = 0
    for p in closed:
        running += p.pnl_cents or 0
        points.append({
            "timestamp": p.closed_at,
            "cumulative_pnl_cents": running,
        })

    # Extend to current time
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    if points[-1]["timestamp"] != now:
        points.append({
            "timestamp": now,
            "cumulative_pnl_cents": running,
        })

    return points


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
