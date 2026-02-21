---
name: kalshi-weather
description: Trade Kalshi weather prediction markets using GFS ensemble forecasts for edge detection. Paper trading by default.
homepage: https://kalshi.com
metadata: {"moltx":{"emoji":"🌡️","requires":{"bins":["uv"]}}}
---

# Kalshi Weather Trading

Trade weather prediction markets on Kalshi using GFS 31-member ensemble forecasts to detect pricing edges. **Paper trading by default** ($1000 virtual balance). Add `--live` for real API trading.

## Paper Trading (default, no API key needed for trades)

Check paper balance:
```bash
uv run {baseDir}/scripts/kalshi.py balance
```

Paper buy (specify price in cents with --price, or auto-fetch from Kalshi):
```bash
uv run {baseDir}/scripts/kalshi.py buy KXHIGHNY-26FEB22-T40 yes 50 --price 65
```

Paper sell:
```bash
uv run {baseDir}/scripts/kalshi.py sell KXHIGHNY-26FEB22-T40 yes --price 70
```

Settle paper position after market closes (won/lost):
```bash
uv run {baseDir}/scripts/kalshi.py settle KXHIGHNY-26FEB22-T40 won
```

View positions + P&L:
```bash
uv run {baseDir}/scripts/kalshi.py positions
```

Trade history:
```bash
uv run {baseDir}/scripts/kalshi.py history
```

Reset paper account to $1000:
```bash
uv run {baseDir}/scripts/kalshi.py reset
```

## Weather Edge Detection

GFS ensemble edge detection for a city:
```bash
uv run {baseDir}/scripts/kalshi.py edge CITY
```
Cities: `NY`, `CHI`, `LAX`, `MIA`, `DEN`, `AUS`

Scan all cities for edge opportunities:
```bash
uv run {baseDir}/scripts/kalshi.py scan
```

## Live/Demo API Commands (requires KALSHI_API_KEY_ID + KALSHI_PRIVATE_KEY_PATH)

```bash
uv run {baseDir}/scripts/kalshi.py --live markets
uv run {baseDir}/scripts/kalshi.py --live market TICKER
uv run {baseDir}/scripts/kalshi.py --live balance
uv run {baseDir}/scripts/kalshi.py --live buy TICKER yes 5
uv run {baseDir}/scripts/kalshi.py --live sell TICKER yes 5
```

## Notes

- Paper trading tracks positions locally in `~/.openclaw/kalshi-weather/positions.json`
- Add `--json` to any command for structured JSON output
- Edge detection uses quarter-Kelly sizing capped at 5% of balance, minimum 8% edge threshold
- Weather data from Open-Meteo GFS ensemble (free, no API key)
- Settlement based on NWS Daily Climate Report, next morning
- For live trading: set `KALSHI_ENV=demo` (default) or `KALSHI_ENV=prod`
