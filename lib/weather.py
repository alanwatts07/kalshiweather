"""GFS 31-member ensemble forecasts from Open-Meteo for weather edge detection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Optional

import httpx

from lib.config import KELLY_FRACTION, MAX_POSITION_PCT, MIN_EDGE_PCT, City

ENSEMBLE_URL = "https://ensemble-api.open-meteo.com/v1/ensemble"


@dataclass
class EnsembleForecast:
    """Holds ensemble forecast members for a city/date."""

    city: City
    target_date: date
    members: list[float]  # temperature values (F) from each ensemble member

    @property
    def count(self) -> int:
        return len(self.members)

    @property
    def mean(self) -> float:
        return sum(self.members) / len(self.members) if self.members else 0

    @property
    def spread(self) -> float:
        if not self.members:
            return 0
        return max(self.members) - min(self.members)

    def probability_above(self, threshold: float) -> float:
        """Fraction of ensemble members with temp >= threshold."""
        if not self.members:
            return 0
        return sum(1 for t in self.members if t >= threshold) / len(self.members)

    def probability_below(self, threshold: float) -> float:
        """Fraction of ensemble members with temp < threshold."""
        return 1.0 - self.probability_above(threshold)

    def probability_between(self, low: float, high: float) -> float:
        """Fraction of ensemble members with low <= temp < high."""
        if not self.members:
            return 0
        return sum(1 for t in self.members if low <= t < high) / len(self.members)


def fetch_ensemble(city: City, target_date: Optional[date] = None) -> EnsembleForecast:
    """Fetch GFS ensemble high temp forecast for a city."""
    if target_date is None:
        target_date = date.today() + timedelta(days=1)

    params = {
        "latitude": city.lat,
        "longitude": city.lon,
        "models": "gfs_seamless",
        "daily": "temperature_2m_max",
        "temperature_unit": "fahrenheit",
        "start_date": target_date.isoformat(),
        "end_date": target_date.isoformat(),
    }

    resp = httpx.get(ENSEMBLE_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    members = _extract_members(data, target_date)
    return EnsembleForecast(city=city, target_date=target_date, members=members)


def _extract_members(data: dict[str, Any], target_date: date) -> list[float]:
    """Extract all ensemble member values for the target date."""
    daily = data.get("daily", {})
    times = daily.get("time", [])
    target_str = target_date.isoformat()

    # Find the index for our target date
    try:
        idx = times.index(target_str)
    except ValueError:
        # Try to find it in the first position
        idx = 0

    members = []
    for key, values in daily.items():
        if key == "time":
            continue
        # Keys look like "temperature_2m_max_member01", etc.
        if key.startswith("temperature_2m_max") and isinstance(values, list) and idx < len(values):
            val = values[idx]
            if val is not None:
                members.append(float(val))

    return members


@dataclass
class EdgeOpportunity:
    """A detected pricing edge."""

    ticker: str
    city_code: str
    threshold: float
    side: str           # "yes" or "no"
    ensemble_prob: float
    market_price: float  # in cents
    edge_pct: float
    kelly_fraction: float
    suggested_contracts: int


def calculate_edges(
    forecast: EnsembleForecast,
    market_prices: dict[str, dict[str, Any]],
    balance_cents: int = 10000,
) -> list[EdgeOpportunity]:
    """Compare ensemble probabilities to market prices, find edges.

    market_prices: dict of ticker -> {"yes_price": int, "no_price": int, "threshold": float}
    """
    edges: list[EdgeOpportunity] = []

    for ticker, info in market_prices.items():
        threshold = info["threshold"]
        yes_price = info.get("yes_price", 50)
        no_price = info.get("no_price", 50)

        # Ensemble probability that high temp >= threshold
        prob_yes = forecast.probability_above(threshold)
        prob_no = 1.0 - prob_yes

        # Check YES side edge
        implied_yes = yes_price / 100.0
        if implied_yes > 0:
            edge_yes = (prob_yes - implied_yes) / implied_yes * 100
            if edge_yes >= MIN_EDGE_PCT:
                kelly = _kelly_size(prob_yes, implied_yes, balance_cents, yes_price)
                edges.append(EdgeOpportunity(
                    ticker=ticker,
                    city_code=forecast.city.code,
                    threshold=threshold,
                    side="yes",
                    ensemble_prob=prob_yes,
                    market_price=yes_price,
                    edge_pct=edge_yes,
                    kelly_fraction=kelly["fraction"],
                    suggested_contracts=kelly["contracts"],
                ))

        # Check NO side edge
        implied_no = no_price / 100.0
        if implied_no > 0:
            edge_no = (prob_no - implied_no) / implied_no * 100
            if edge_no >= MIN_EDGE_PCT:
                kelly = _kelly_size(prob_no, implied_no, balance_cents, no_price)
                edges.append(EdgeOpportunity(
                    ticker=ticker,
                    city_code=forecast.city.code,
                    threshold=threshold,
                    side="no",
                    ensemble_prob=prob_no,
                    market_price=no_price,
                    edge_pct=edge_no,
                    kelly_fraction=kelly["fraction"],
                    suggested_contracts=kelly["contracts"],
                ))

    # Sort by edge size descending
    edges.sort(key=lambda e: e.edge_pct, reverse=True)
    return edges


def _kelly_size(
    prob: float,
    implied: float,
    balance_cents: int,
    price_cents: int,
) -> dict[str, Any]:
    """Quarter-Kelly sizing capped at MAX_POSITION_PCT of balance."""
    if implied >= 1.0 or implied <= 0:
        return {"fraction": 0, "contracts": 0}

    # Kelly: f* = (p * (b+1) - 1) / b  where b = (1/implied - 1)
    b = (1.0 / implied) - 1.0
    if b <= 0:
        return {"fraction": 0, "contracts": 0}

    full_kelly = (prob * (b + 1) - 1) / b
    quarter_kelly = max(0, full_kelly * KELLY_FRACTION)

    # Cap at MAX_POSITION_PCT of balance
    max_dollars = balance_cents / 100.0 * (MAX_POSITION_PCT / 100.0)
    kelly_dollars = balance_cents / 100.0 * quarter_kelly
    dollars = min(kelly_dollars, max_dollars)

    contracts = int(dollars / (price_cents / 100.0)) if price_cents > 0 else 0
    return {"fraction": quarter_kelly, "contracts": max(0, contracts)}
