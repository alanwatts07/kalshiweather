#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "httpx>=0.27.0",
# ]
# ///
"""
Train GFS bias corrections from historical forecast vs actual data.

Fetches ~12 months of GFS deterministic forecasts and observed daily highs
from Open-Meteo, computes per-station per-month mean bias, and saves
corrections JSON for runtime ensemble adjustment.

Usage:
    uv run scripts/train_bias.py [--months 12] [--verbose]
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.bias import BiasCorrections, MonthlyBias
from lib.config import CITIES

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
HISTORICAL_FORECAST_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"


def fetch_daily_highs(url: str, city, start: str, end: str) -> dict[str, float]:
    """Fetch daily temperature_2m_max → {date_str: temp_f}."""
    params = {
        "latitude": city.lat,
        "longitude": city.lon,
        "daily": "temperature_2m_max",
        "temperature_unit": "fahrenheit",
        "start_date": start,
        "end_date": end,
    }
    resp = httpx.get(url, params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    daily = data.get("daily", {})
    times = daily.get("time", [])
    temps = daily.get("temperature_2m_max", [])
    return {d: t for d, t in zip(times, temps) if t is not None}


def compute_monthly_biases(
    forecasts: dict[str, float],
    actuals: dict[str, float],
) -> dict[int, MonthlyBias]:
    """Compute per-month bias stats from paired forecast/actual data."""
    errors_by_month: dict[int, list[float]] = defaultdict(list)

    for date_str in forecasts:
        if date_str in actuals:
            fc = forecasts[date_str]
            obs = actuals[date_str]
            month = int(date_str.split("-")[1])
            errors_by_month[month].append(fc - obs)

    biases: dict[int, MonthlyBias] = {}
    for month in sorted(errors_by_month):
        errs = errors_by_month[month]
        if len(errs) >= 2:
            biases[month] = MonthlyBias(
                mean_bias=round(statistics.mean(errs), 2),
                std_error=round(statistics.stdev(errs), 2),
                samples=len(errs),
            )
        elif len(errs) == 1:
            biases[month] = MonthlyBias(
                mean_bias=round(errs[0], 2),
                std_error=0.0,
                samples=1,
            )
    return biases


def main():
    parser = argparse.ArgumentParser(description="Train GFS bias corrections")
    parser.add_argument("--months", type=int, default=12, help="Months of history (default: 12)")
    parser.add_argument("--verbose", action="store_true", help="Print per-city details")
    args = parser.parse_args()

    end_date = date.today().replace(day=1) - timedelta(days=1)  # end of last month
    start_date = end_date - timedelta(days=args.months * 31)
    start_date = start_date.replace(day=1)  # start of that month

    start_str = start_date.isoformat()
    end_str = end_date.isoformat()

    print(f"Training bias corrections: {start_str} to {end_str}")
    print(f"Cities: {', '.join(CITIES.keys())}\n")

    all_corrections: dict[str, dict[str, MonthlyBias]] = {}

    for code, city in CITIES.items():
        print(f"  {city.name} ({code})...")

        try:
            actuals = fetch_daily_highs(ARCHIVE_URL, city, start_str, end_str)
            time.sleep(0.5)

            forecasts = fetch_daily_highs(HISTORICAL_FORECAST_URL, city, start_str, end_str)
            time.sleep(0.5)
        except Exception as e:
            print(f"    ERROR: {e}")
            continue

        biases = compute_monthly_biases(forecasts, actuals)
        all_corrections[code] = {str(m): b for m, b in biases.items()}

        paired = sum(b.samples for b in biases.values())
        print(f"    {len(actuals)} actual days, {len(forecasts)} forecast days, {paired} paired")

        if args.verbose:
            for month in sorted(biases, key=int):
                b = biases[month]
                direction = "warm" if b.mean_bias > 0 else "cool"
                print(f"    Month {month:>2}: bias={b.mean_bias:+.1f}F ({direction}), "
                      f"std={b.std_error:.1f}F, n={b.samples}")

    corrections = BiasCorrections(
        version=1,
        trained_at=datetime.now().isoformat(timespec="seconds"),
        training_start=start_str,
        training_end=end_str,
        corrections=all_corrections,
    )
    corrections.save()

    print(f"\nSaved bias corrections to {corrections.__class__.__name__} file")
    print(f"  Cities: {len(all_corrections)}")
    total_months = sum(len(m) for m in all_corrections.values())
    print(f"  Total month entries: {total_months}")


if __name__ == "__main__":
    main()
