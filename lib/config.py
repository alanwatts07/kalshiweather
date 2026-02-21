"""City configurations, environment helpers, and constants."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class City:
    code: str
    name: str
    lat: float
    lon: float
    nws_station: str
    series_ticker: str  # Kalshi series ticker prefix


CITIES: dict[str, City] = {
    "NY": City("NY", "New York", 40.7128, -74.0060, "KNYC", "KXHIGHNY"),
    "CHI": City("CHI", "Chicago", 41.8781, -87.6298, "KORD", "KXHIGHCHI"),
    "LAX": City("LAX", "Los Angeles", 34.0522, -118.2437, "KLAX", "KXHIGHLAX"),
    "MIA": City("MIA", "Miami", 25.7617, -80.1918, "KMIA", "KXHIGHMI"),
    "DEN": City("DEN", "Denver", 39.7392, -104.9903, "KDEN", "KXHIGHDEN"),
    "AUS": City("AUS", "Austin", 30.2672, -97.7431, "KAUS", "KXHIGHAUS"),
}

# API base URLs
DEMO_API_BASE = "https://demo-api.kalshi.co/trade-api/v2"
PROD_API_BASE = "https://api.elections.kalshi.com/trade-api/v2"

# Rate limits (basic tier)
READ_RATE_LIMIT = 20   # per second
WRITE_RATE_LIMIT = 10  # per second

# Edge detection defaults
MIN_EDGE_PCT = 8.0          # minimum edge % to flag
KELLY_FRACTION = 0.25       # quarter-Kelly
MAX_POSITION_PCT = 5.0      # max 5% of balance per position


def get_api_base() -> str:
    env = os.environ.get("KALSHI_ENV", "demo").lower()
    if env == "prod":
        return PROD_API_BASE
    return DEMO_API_BASE


def get_api_key_id() -> str:
    val = os.environ.get("KALSHI_API_KEY_ID", "")
    if not val:
        raise RuntimeError("KALSHI_API_KEY_ID not set")
    return val


def get_private_key_path() -> str:
    val = os.environ.get("KALSHI_PRIVATE_KEY_PATH", "")
    if not val:
        raise RuntimeError("KALSHI_PRIVATE_KEY_PATH not set")
    return val


def is_demo() -> bool:
    return os.environ.get("KALSHI_ENV", "demo").lower() != "prod"
