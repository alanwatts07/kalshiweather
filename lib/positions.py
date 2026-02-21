"""Local JSON position tracking and paper trading for Kalshi weather trades."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

POSITIONS_DIR = Path.home() / ".openclaw" / "kalshi-weather"
POSITIONS_FILE = POSITIONS_DIR / "positions.json"

PAPER_STARTING_BALANCE_CENTS = 100_000  # $1000


@dataclass
class Position:
    ticker: str
    side: str           # "yes" or "no"
    contracts: int
    avg_price_cents: int
    opened_at: str
    closed_at: Optional[str] = None
    close_price_cents: Optional[int] = None
    mode: str = "paper"  # "paper" or "live"

    @property
    def is_open(self) -> bool:
        return self.closed_at is None

    @property
    def cost_cents(self) -> int:
        return self.contracts * self.avg_price_cents

    @property
    def pnl_cents(self) -> Optional[int]:
        if self.close_price_cents is None:
            return None
        return self.contracts * (self.close_price_cents - self.avg_price_cents)


@dataclass
class PositionStore:
    positions: list[Position] = field(default_factory=list)
    paper_balance_cents: int = PAPER_STARTING_BALANCE_CENTS
    total_deposited_cents: int = PAPER_STARTING_BALANCE_CENTS

    @classmethod
    def load(cls) -> PositionStore:
        if not POSITIONS_FILE.exists():
            return cls()
        data = json.loads(POSITIONS_FILE.read_text())
        positions = [Position(**p) for p in data.get("positions", [])]
        return cls(
            positions=positions,
            paper_balance_cents=data.get("paper_balance_cents", PAPER_STARTING_BALANCE_CENTS),
            total_deposited_cents=data.get("total_deposited_cents", PAPER_STARTING_BALANCE_CENTS),
        )

    def save(self) -> None:
        POSITIONS_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "paper_balance_cents": self.paper_balance_cents,
            "total_deposited_cents": self.total_deposited_cents,
            "positions": [asdict(p) for p in self.positions],
        }
        POSITIONS_FILE.write_text(json.dumps(data, indent=2))

    def paper_buy(self, ticker: str, side: str, contracts: int, price_cents: int) -> Position:
        """Paper trade buy — deducts from virtual balance."""
        cost = contracts * price_cents
        if cost > self.paper_balance_cents:
            raise ValueError(
                f"Insufficient paper balance: need ${cost/100:.2f}, have ${self.paper_balance_cents/100:.2f}"
            )
        self.paper_balance_cents -= cost
        pos = Position(
            ticker=ticker,
            side=side.lower(),
            contracts=contracts,
            avg_price_cents=price_cents,
            opened_at=datetime.utcnow().isoformat(),
            mode="paper",
        )
        self.positions.append(pos)
        self.save()
        return pos

    def paper_sell(self, ticker: str, side: str, price_cents: int) -> Optional[Position]:
        """Paper trade sell — credits virtual balance."""
        for pos in self.positions:
            if pos.ticker == ticker and pos.side == side.lower() and pos.is_open and pos.mode == "paper":
                proceeds = pos.contracts * price_cents
                self.paper_balance_cents += proceeds
                pos.closed_at = datetime.utcnow().isoformat()
                pos.close_price_cents = price_cents
                self.save()
                return pos
        return None

    def paper_settle(self, ticker: str, won: bool) -> Optional[Position]:
        """Settle a paper position. If won, credit $1/contract (100¢). If lost, nothing."""
        for pos in self.positions:
            if pos.ticker == ticker and pos.is_open and pos.mode == "paper":
                if won:
                    self.paper_balance_cents += pos.contracts * 100
                pos.close_price_cents = 100 if won else 0
                pos.closed_at = datetime.utcnow().isoformat()
                self.save()
                return pos
        return None

    def open_position(self, ticker: str, side: str, contracts: int, price_cents: int) -> Position:
        pos = Position(
            ticker=ticker,
            side=side.lower(),
            contracts=contracts,
            avg_price_cents=price_cents,
            opened_at=datetime.utcnow().isoformat(),
            mode="live",
        )
        self.positions.append(pos)
        self.save()
        return pos

    def close_position(self, ticker: str, side: str, price_cents: int) -> Optional[Position]:
        for pos in self.positions:
            if pos.ticker == ticker and pos.side == side.lower() and pos.is_open:
                pos.closed_at = datetime.utcnow().isoformat()
                pos.close_price_cents = price_cents
                self.save()
                return pos
        return None

    def open_positions(self) -> list[Position]:
        return [p for p in self.positions if p.is_open]

    def closed_positions(self) -> list[Position]:
        return [p for p in self.positions if not p.is_open]

    @property
    def paper_equity_cents(self) -> int:
        """Total paper equity = cash + open position cost basis."""
        open_cost = sum(p.cost_cents for p in self.open_positions() if p.mode == "paper")
        return self.paper_balance_cents + open_cost

    @property
    def paper_pnl_cents(self) -> int:
        """Total paper P&L = equity - total deposited."""
        return self.paper_equity_cents - self.total_deposited_cents

    @property
    def realized_pnl_cents(self) -> int:
        """Sum of realized P&L from closed paper positions."""
        return sum(p.pnl_cents or 0 for p in self.positions if not p.is_open and p.mode == "paper")
