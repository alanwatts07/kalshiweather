"""GFS 31-member ensemble forecasts from Open-Meteo for weather edge detection."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Optional

import httpx

from lib.config import KELLY_FRACTION, MAX_POSITION_PCT, MIN_EDGE_PCT, MIN_PRICE_CENTS, City

ENSEMBLE_URL = "https://ensemble-api.open-meteo.com/v1/ensemble"


@dataclass
class EnsembleForecast:
    """Holds ensemble forecast members for a city/date."""

    city: City
    target_date: date
    members: list[float]  # temperature values (F) from each ensemble member
    bias_applied: bool = False
    bias_shift: float | None = None

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
        """Probability temp >= threshold using Gaussian fit to ensemble.

        Fits a normal distribution to the ensemble members and uses the CDF,
        which gives smooth tail probabilities instead of 0%/100% from raw
        member counting with only 31 samples. A minimum stdev floor of 1.5°F
        accounts for model uncertainty beyond ensemble spread.
        """
        if not self.members:
            return 0
        n = len(self.members)
        mu = sum(self.members) / n
        variance = sum((t - mu) ** 2 for t in self.members) / n
        sigma = max(math.sqrt(variance), 1.5)  # floor: 1.5°F minimum uncertainty
        # P(temp >= threshold) = 1 - Φ((threshold - mu) / sigma)
        z = (threshold - mu) / sigma
        prob = 1.0 - 0.5 * (1.0 + math.erf(z / math.sqrt(2)))
        return max(0.01, min(0.99, prob))  # clamp to [1%, 99%]

    def probability_below(self, threshold: float) -> float:
        """Fraction of ensemble members with temp < threshold."""
        return 1.0 - self.probability_above(threshold)

    def probability_between(self, low: float, high: float) -> float:
        """P(low <= temp <= high) using Gaussian CDF consistent with probability_above()."""
        p_ge_low = self.probability_above(low)
        p_ge_high_next = self.probability_above(high + 1)
        return max(0.01, min(0.99, p_ge_low - p_ge_high_next))


def _apply_bias(
    members: list[float], city: City, target_date: date
) -> tuple[list[float], bool, float | None]:
    """Apply bias correction to ensemble members. Returns (members, applied, shift).

    Fails silently — bias is never a blocker for forecasting.
    """
    try:
        from lib.bias import BiasCorrections, apply_bias_correction

        corrections = BiasCorrections.load()
        if corrections is None:
            return members, False, None

        bias = corrections.get_bias(city.code, target_date.month)
        if bias is None or bias.samples < 10:
            return members, False, None

        corrected = apply_bias_correction(members, bias)
        return corrected, True, round(-bias.mean_bias, 2)
    except Exception:
        return members, False, None


def fetch_ensemble(
    city: City,
    target_date: Optional[date] = None,
    apply_correction: bool = True,
) -> EnsembleForecast:
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

    bias_applied = False
    bias_shift = None
    if apply_correction:
        members, bias_applied, bias_shift = _apply_bias(members, city, target_date)

    return EnsembleForecast(
        city=city,
        target_date=target_date,
        members=members,
        bias_applied=bias_applied,
        bias_shift=bias_shift,
    )


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
    strike_type: str = "greater"  # "greater", "less", "between"


def calculate_edges(
    forecast: EnsembleForecast,
    market_prices: dict[str, dict[str, Any]],
    balance_cents: int = 10000,
) -> list[EdgeOpportunity]:
    """Compare ensemble probabilities to market prices, find edges.

    market_prices: dict of ticker -> {
        "strike_type": "greater"|"less"|"between",
        "floor_strike": float|None, "cap_strike": float|None,
        "yes_price": int, "no_price": int,
    }
    """
    edges: list[EdgeOpportunity] = []

    for ticker, info in market_prices.items():
        strike_type = info.get("strike_type", "greater")
        floor_strike = info.get("floor_strike")
        cap_strike = info.get("cap_strike")
        yes_price = info.get("yes_price", 50)
        no_price = info.get("no_price", 50)

        # Calculate ensemble P(YES) based on market type
        if strike_type == "greater":
            # YES = temp > floor → P(T >= floor+1)
            threshold = floor_strike
            prob_yes = forecast.probability_above(floor_strike + 1)
        elif strike_type == "less":
            # YES = temp < cap → 1 - P(T >= cap)
            threshold = cap_strike
            prob_yes = 1.0 - forecast.probability_above(cap_strike)
        elif strike_type == "between":
            # YES = floor <= temp <= cap → P(T >= floor) - P(T >= cap+1)
            threshold = floor_strike  # display value
            prob_yes = forecast.probability_between(floor_strike, cap_strike)
        else:
            continue  # unknown strike_type, skip

        prob_no = 1.0 - prob_yes

        # Check YES side edge (skip if price below floor)
        implied_yes = yes_price / 100.0
        if implied_yes > 0 and yes_price >= MIN_PRICE_CENTS:
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
                    strike_type=strike_type,
                ))

        # Check NO side edge (skip if price below floor)
        implied_no = no_price / 100.0
        if implied_no > 0 and no_price >= MIN_PRICE_CENTS:
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
                    strike_type=strike_type,
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
