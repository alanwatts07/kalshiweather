# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Kalshi weather prediction market trading CLI. Uses GFS 31-member ensemble forecasts from Open-Meteo to detect pricing edges on Kalshi temperature markets (daily high temp). Paper trading by default ($1000 virtual balance); `--live` flag for real API trading.

## Running Commands

All commands use `uv run` (inline script dependencies in `scripts/kalshi.py` — no requirements.txt/pyproject.toml):

```bash
uv run scripts/kalshi.py <command> [--live] [--json]
```

Key commands: `scan`, `edge CITY`, `buy`, `sell`, `settle`, `balance`, `positions`, `history`, `reset`, `markets`, `market TICKER`.

City codes: `NY`, `CHI`, `LAX`, `MIA`, `DEN`, `AUS`.

## Architecture

```
scripts/kalshi.py    # CLI entrypoint — argparse, command dispatch, all user-facing output
lib/
  config.py          # City dataclass, CITIES dict, env helpers, edge detection constants
  auth.py            # RSA-PSS (SHA-256) HMAC signing for Kalshi API requests
  client.py          # KalshiClient — thin httpx wrapper over Kalshi trade API v2
  weather.py         # EnsembleForecast + fetch_ensemble() from Open-Meteo, edge calculation + Kelly sizing
  positions.py       # PositionStore — JSON-backed paper/live position tracking
```

### Data Flow

1. `fetch_ensemble()` (weather.py) calls Open-Meteo GFS ensemble API → returns `EnsembleForecast` with 31 temperature members
2. `KalshiClient.get_markets()` fetches current market prices by series ticker (e.g., `KXHIGHNY`)
3. `calculate_edges()` compares ensemble probability distribution to market-implied probabilities → returns `EdgeOpportunity` list for edges >= 8%
4. Position sizing uses quarter-Kelly capped at 5% of balance (`_kelly_size()` in weather.py)

### Key Design Decisions

- **Paper trading is completely local** — positions stored in `~/.openclaw/kalshi-weather/positions.json`, no API keys needed
- **Live trading requires env vars**: `KALSHI_API_KEY_ID`, `KALSHI_PRIVATE_KEY_PATH`, and optionally `KALSHI_ENV` (default: `demo`, set to `prod` for real money)
- **Ticker format**: `KXHIGHNY-26FEB22-T40` — series ticker + date + temperature threshold. `_parse_threshold()` in kalshi.py extracts the `T{n}` value
- **Edge calculation**: `(ensemble_prob - market_implied) / market_implied * 100` — minimum 8% threshold (`MIN_EDGE_PCT` in config.py)
- **Dependencies are declared inline** in the script header (PEP 723): `cryptography` and `httpx` only

## Strategy Context

See `STRATEGY.md` for the full trading strategy reference including:
- Kalshi API rate limits and efficient usage patterns
- GFS/HRRR run schedules and data availability windows
- NWS settlement data (CLI reports) and DSM release times by city
- Kelly criterion sizing rationale (quarter-Kelly default)
- Known bot behavior on Kalshi weather markets
- Optimal trading windows (morning 6-10 AM ET is prime edge window)
