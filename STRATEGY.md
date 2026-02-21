# Kalshi Weather Market Trading Bot -- Strategy & Operations Guide

Actionable reference for running an automated weather prediction market bot on Kalshi,
optimized for cost, API efficiency, and edge detection.

---

## Table of Contents

1. [Kalshi API Rate Limits & Efficient Usage](#1-kalshi-api-rate-limits--efficient-usage)
2. [Weather Data: Open-Meteo, GFS Ensemble, HRRR](#2-weather-data-open-meteo-gfs-ensemble-hrrr)
3. [NWS Data Release Schedule (Critical for Edge)](#3-nws-data-release-schedule-critical-for-edge)
4. [Scheduling: When to Poll, When to Trade](#4-scheduling-when-to-poll-when-to-trade)
5. [Market Liquidity & Edge Windows](#5-market-liquidity--edge-windows)
6. [OpenClaw Skill Cost Optimization](#6-openclaw-skill-cost-optimization)
7. [Kelly Criterion -- Practical Sizing](#7-kelly-criterion----practical-sizing)
8. [Architecture Reference](#8-architecture-reference)

---

## 1. Kalshi API Rate Limits & Efficient Usage

### Rate Limit Tiers

| Tier     | Read Limit | Write Limit | How to Get                                |
|----------|-----------|------------|-------------------------------------------|
| Basic    | 20/sec    | 10/sec     | Signup (default)                          |
| Advanced | 30/sec    | 30/sec     | Apply via kalshi.typeform.com/advanced-api |
| Premier  | 100/sec   | 100/sec    | 3.75% of monthly exchange volume          |
| Prime    | 400/sec   | 400/sec    | 7.5% of monthly exchange volume           |

**Write-limited endpoints** (each counts as 1 write):
- `CreateOrder`, `CancelOrder`, `AmendOrder`, `DecreaseOrder`
- `BatchCreateOrders` (each item = 1 write)
- `BatchCancelOrders` (each item = 0.2 writes)

### Minimizing REST Calls

1. **Use WebSocket for market data.** Kalshi offers public WebSocket channels (`ticker`,
   `trade`, `market_lifecycle_v2`, `multivariate`). Subscribe to `ticker` for price
   updates instead of polling `GET /markets/{ticker}`. This eliminates 90%+ of read
   traffic. No auth required for public channels.

2. **Cache market metadata.** Market tickers, strike ranges, and expiry times change
   infrequently. Fetch the full market list once at startup, refresh every 6 hours.

3. **Batch operations.** Use `BatchCreateOrders` and `BatchCancelOrders` to manage
   positions in a single API call instead of multiple individual calls.

4. **Conditional polling.** Only poll the REST API for account balance and position
   details. These change only when you trade, so poll every 60s or after a trade event.

5. **Local order book.** Maintain a local copy of the order book via WebSocket deltas.
   Only fall back to REST snapshot if the WebSocket disconnects.

### Practical Rate Budget (Basic Tier)

At Basic tier (20 read/sec, 10 write/sec), a weather bot needs very little:
- Weather markets: ~4 cities x ~10-15 temperature brackets = 40-60 contracts
- Scanning all contracts once: 1 REST call (list markets by event)
- Trading: typically 0-5 orders per scan cycle
- **You will never hit Basic tier limits with a weather bot.** Save your budget for
  data freshness, not volume.

### Authentication

```
# REST: API-key + HMAC signature in headers
# WebSocket: same auth in connection headers
# Tokens expire -- handle 401s gracefully with re-auth
```

---

## 2. Weather Data: Open-Meteo, GFS Ensemble, HRRR

### GFS Ensemble (Primary Probabilistic Source)

The GFS Ensemble (GEFS) is the backbone of probabilistic temperature forecasting.

| Model             | Resolution | Members | Forecast | Updates      |
|-------------------|-----------|---------|----------|--------------|
| GFS Ensemble 0.25 | 25 km     | 31      | 10 days  | Every 6 hours |
| GFS Ensemble 0.5  | 50 km     | 31      | 35 days  | Every 6 hours |
| GFS deterministic | 13 km     | 1       | 16 days  | Every 6 hours |
| HRRR              | 3 km      | 1       | 18/48 hr | Every hour   |

### GFS Run Schedule & Data Availability

GFS initializes at **00Z, 06Z, 12Z, 18Z** (4x daily).

| Init Time | Data Available (approx) | US Eastern     |
|-----------|------------------------|----------------|
| 00Z       | ~03:30-03:45 UTC       | ~10:30-10:45 PM |
| 06Z       | ~09:30-09:45 UTC       | ~4:30-4:45 AM   |
| 12Z       | ~15:30-15:45 UTC       | ~10:30-10:45 AM |
| 18Z       | ~21:30-21:45 UTC       | ~4:30-4:45 PM   |

**Latency: ~3.5 hours from init to availability.** Open-Meteo ingests NOAA data as
soon as it is released, then needs an additional ~10 minutes for full server
propagation across their CDN.

### HRRR (High-Resolution Intraday Source)

HRRR updates **every hour** with 3km resolution -- far superior to GFS for same-day
temperature forecasts. Extended 48-hour forecasts available at 00, 06, 12, 18Z runs.

**Key advantage:** HRRR assimilates radar data every 15 minutes, catching mesoscale
phenomena (cloud cover changes, frontal passages) that GFS misses. For same-day
trading, HRRR is your primary model.

### Open-Meteo Free Tier Limits

| Constraint         | Limit        |
|-------------------|-------------|
| Daily requests    | 10,000      |
| Hourly requests   | 5,000       |
| Per-minute        | 600         |
| Commercial use    | Requires paid API key |

### Optimal Polling Strategy for Open-Meteo

**Do NOT poll continuously.** Weather data updates on a fixed schedule:

```
# Efficient polling schedule (all times UTC):
# After each GFS run becomes available:
POLL_TIMES_GFS = ["03:45", "09:45", "15:45", "21:45"]

# After HRRR updates (hourly, but only poll during trading hours):
# Trade day = day before settlement through settlement morning
POLL_TIMES_HRRR = ["every hour from 10:00 to 23:59 UTC on trade day"]

# Total daily API calls for 4 cities:
#   GFS ensemble: 4 polls x 4 cities = 16 calls
#   HRRR: 14 polls x 4 cities = 56 calls
#   NWS cross-check: ~20 calls
#   Total: ~92 calls/day (well under 10,000 limit)
```

### API Call Example

```python
import requests

# GFS Ensemble for NYC (Central Park / KNYC area)
params = {
    "latitude": 40.78,
    "longitude": -73.97,
    "daily": "temperature_2m_max",
    "temperature_unit": "fahrenheit",
    "timezone": "America/New_York",
    "models": "gfs_seamless",  # or "gfs025" for ensemble
    "forecast_days": 2
}
resp = requests.get("https://ensemble-api.open-meteo.com/v1/ensemble", params=params)
data = resp.json()
# data["daily"]["temperature_2m_max"] -> list of 31 ensemble member forecasts
```

---

## 3. NWS Data Release Schedule (Critical for Edge)

NWS data drives both real-time price moves and final settlement. Understanding the
release schedule is essential.

### Settlement Source

Kalshi settles ALL weather markets on the **NWS Climatological Report (CLI)**:
- Reporting period: 12:00 AM to 11:59 PM **Local Standard Time**
- Issued sometime after midnight LST (typically early morning)
- Settlement/expiration: **10:00 AM ET** the following day

### Key NWS Data Products

| Product | Description | Frequency | Trading Impact |
|---------|------------|-----------|---------------|
| **CLI** | Official daily climate report | Once/day (after midnight LST) | Final settlement source |
| **DSM** | Daily Summary Message | 2-3x/day per city | Reveals running daily high; bots react instantly |
| **Hourly Obs** | METAR/ASOS observations | ~:51-:54 past each hour | Updates current temperature |
| **6-Hour Max** | Max temp in 6hr window | Every 6 hours (~:51Z) | Can reveal missed highs |

### DSM Release Times by City (UTC)

| City    | DSM Times (UTC)               |
|---------|-------------------------------|
| NYC     | 20:21Z, 21:21Z, 05:17Z       |
| Chicago | 21:17Z, 22:17Z, 06:17Z       |
| Miami   | 07:22Z, 20:12Z, 21:12Z, 05:17Z |

### 6-Hour Observation Windows

Released at approximately **23:51Z, 05:51Z, 11:51Z, 17:51Z** -- these can contain
a 6-hour maximum temperature that other data sources miss.

### Bot Awareness

Known automated traders operate on Kalshi weather markets:

- **DSM Bot**: Instantly reacts to DSM releases. If a DSM reveals a new daily high,
  this bot will sweep any mispriced limit orders within milliseconds.
- **OMO Bot**: Monitors 1-minute ASOS observations. Has faster access to temperature
  data than public 5-minute feeds.
- **6-Hour Bot**: Reacts to 6-hourly max temperature in NWS hourly observations.
- **"240" Market Maker**: Provides continuous two-sided liquidity with narrow spreads.
  Adjusts pricing based on internal forecast model.

**Implication:** Do NOT leave resting limit orders at vulnerable prices near DSM
release times. Pull or adjust orders 5 minutes before expected DSM windows.

---

## 4. Scheduling: When to Poll, When to Trade

### Recommended Cron Schedule

Continuous polling wastes resources. Use cron-based scheduling aligned to data updates:

```cron
# === GFS Ensemble Scan (4x daily, after data available) ===
# Check Open-Meteo for fresh GFS, compare to Kalshi prices, signal if edge
50 3,9,15,21 * * *  /path/to/scan_gfs_ensemble.sh

# === HRRR Intraday Scan (hourly during active trading) ===
# Run during the temperature-relevant hours (10 UTC = 5/6 AM ET through end of day)
5 10-23 * * *  /path/to/scan_hrrr.sh
5 0-5 * * *    /path/to/scan_hrrr.sh  # overnight for next-day setup

# === NWS Data Cross-Check (around DSM release windows) ===
# NYC DSMs at 20:21Z, 21:21Z -- check 5 min after
26 20,21 * * *  /path/to/check_nws_dsm.sh NYC
22 21,22 * * *  /path/to/check_nws_dsm.sh CHI
17 20,21 * * *  /path/to/check_nws_dsm.sh MIA

# === Position Review & Risk Check (2x daily) ===
0 14 * * *   /path/to/review_positions.sh   # morning ET
0 22 * * *   /path/to/review_positions.sh   # evening ET

# === Settlement Monitoring (morning after) ===
0 13 * * *   /path/to/check_settlement.sh   # 8 AM ET, check CLI
```

### Why Cron > Continuous Polling

| Approach | API Calls/Day | LLM Tokens/Day | Latency to Edge |
|----------|--------------|----------------|-----------------|
| Continuous (60s poll) | ~1,440+ | High (every cycle) | <60s |
| Cron (aligned to data) | ~92 | Minimal (only on signal) | <15 min |
| Hybrid (cron + WS) | ~92 REST + WS | Minimal | <60s |

**Recommended: Hybrid approach.** Use cron for weather data polling (data only updates
on a schedule), and a persistent WebSocket for Kalshi market prices (react to price
moves in real time without REST calls).

---

## 5. Market Liquidity & Edge Windows

### When Edges Are Biggest

Weather market edges follow a predictable daily cycle tied to information asymmetry:

#### Evening Before (markets open at 10 AM ET day-before)
- **Edge: MODERATE to HIGH.** Markets open based on 2-3 day forecasts. If the latest
  GFS/ECMWF run has shifted but the market hasn't adjusted, there is edge.
- **Liquidity: THIN.** Few participants in the first hours.
- **Strategy:** Place limit orders at your model price. Low urgency. Let the market
  come to you.

#### Morning of Event Day (6-10 AM ET)
- **Edge: HIGHEST.** The overnight GFS 00Z and 06Z runs may have shifted the forecast
  significantly. The HRRR starts producing hourly updates. Many retail traders
  haven't checked the latest models yet.
- **Liquidity: BUILDING.** Market makers start posting.
- **Strategy:** This is the prime window. Run your ensemble model against current
  market prices. If edge > 8%, place aggressive limit orders near the bid/ask.

#### Midday (10 AM - 2 PM ET)
- **Edge: MODERATE, declining.** As the day progresses, the actual temperature trajectory
  becomes clear. Forecast uncertainty collapses. Markets start pricing the observed
  trend.
- **Liquidity: PEAK.** Most active trading period.
- **Strategy:** Monitor HRRR updates vs market prices. Look for markets that haven't
  reacted to a fresh HRRR update showing a shift.

#### Afternoon / Near Daily High (2-6 PM ET, summer)
- **Edge: LOW to MODERATE but asymmetric.** If the high has already been reached, you
  can sell overpriced upper brackets with high confidence. If the temp is still rising
  unexpectedly, buy upper brackets before bots react to the next hourly obs.
- **Liquidity: MODERATE.**
- **Strategy:** Shift from probabilistic forecasting to observational trading. Watch
  the actual temperature via NWS hourly observations. Compare current temp to the
  brackets being traded.

#### Evening / Post-High (6 PM ET - settlement)
- **Edge: VERY LOW for today's market.** The daily high is usually set. Markets converge
  toward the observed high. Focus shifts to tomorrow's market.
- **Strategy:** Close any remaining positions. Start analyzing tomorrow's market using
  the 18Z GFS run (available ~4:30 PM ET).

### Key Stations (Kalshi Settlement Stations)

| City    | Station | Microclimate Notes |
|---------|---------|-------------------|
| NYC     | KNYC (Central Park) | Urban heat island; can be 2-5F warmer than suburban forecasts |
| Chicago | KORD (O'Hare)      | Lake effect; onshore wind can suppress high by 5-10F |
| Miami   | KMIA               | Sea breeze moderation; humid climate compresses ranges |
| Austin  | KAUS               | Inland Texas; can swing wildly with frontal passages |

---

## 6. OpenClaw Skill Cost Optimization

Running this as an OpenClaw skill for an agent like Max Anvil requires careful token
management. The goal: let deterministic code do the heavy lifting, only invoke the LLM
for genuine decision-making.

### Architecture: Scan Then Decide

```
[Cron Trigger]
    |
    v
[Deterministic Script] -- fetch weather data, compute probabilities
    |                     compare to Kalshi prices, compute edge
    |
    v
[Edge Detected?] --NO--> [Log & Exit. Zero LLM tokens used.]
    |
    YES
    v
[Format Summary] --> [LLM Skill Call] --> [Trade Decision]
                     (only 200-500 tokens)    |
                                              v
                                         [Execute Trade via API]
```

### Token Optimization Rules

1. **Never send raw weather data to the LLM.** Pre-process everything in Python/Node.
   Send the LLM a structured summary:
   ```
   NYC Tomorrow: Model says 73F (68% in 71-75 bracket).
   Market: 71-75 bracket at $0.55. Edge: +13%.
   Recommend: BUY 71-75 YES. Kelly size: $12.
   Confirm or override?
   ```
   This is ~50 tokens instead of sending 31 ensemble members (~500+ tokens).

2. **Move instructions into the skill, not personality files.** Skill instructions
   only load when the skill is invoked. Personality/SOUL.md loads every message.

3. **Keep skill description under 20 words.** The skill list is injected into every
   prompt. Example:
   ```yaml
   ---
   description: Execute weather market trades when edges are detected
   ---
   ```

4. **Batch decisions.** Don't invoke the LLM separately for each city/bracket. Send
   one combined summary of all detected edges and get one batch response:
   ```
   Edges detected:
   1. NYC 71-75 YES: edge +13%, Kelly $12
   2. CHI 55-60 NO: edge +9%, Kelly $8
   3. MIA 85-90 YES: edge +11%, Kelly $10
   Approve all / modify / skip?
   ```

5. **Disable heartbeat context carry.** Use a lightweight standalone heartbeat that
   doesn't load the full session context. Native heartbeat with a large session can
   cost 1000+ tokens per cycle.

6. **Use the cheapest model for the decision.** Weather trade decisions are
   straightforward (approve/reject/modify a pre-computed signal). Use Haiku or
   equivalent. Reserve Sonnet/Opus for complex analysis tasks.

7. **Skip the LLM entirely for auto-approve.** If your confidence in the pipeline is
   high, add an auto-approve mode:
   ```
   if edge > 15% and kelly_size < max_auto_bet:
       execute_trade_directly()  # zero LLM tokens
   elif edge > 8%:
       invoke_llm_for_review()   # ~200 tokens
   else:
       skip()
   ```

### Estimated Token Cost (Per Day)

| Scenario | LLM Calls | Tokens/Day | Cost (Haiku) |
|----------|----------|-----------|-------------|
| No edges found | 0 | 0 | $0.00 |
| 2-3 edges, auto-approved | 0 | 0 | $0.00 |
| 5 edges needing review | 1-2 | ~400-800 | ~$0.001 |
| Active day, 10+ edges | 3-5 | ~1,500 | ~$0.003 |

With auto-approve for high-confidence signals, the LLM cost is essentially zero.

---

## 7. Kelly Criterion -- Practical Sizing

### The Formula

```
Full Kelly fraction = edge / odds

Where:
  edge = your_probability - market_implied_probability
  odds = (1 / market_price) - 1  (for YES contracts)

Example:
  Your model: 68% chance high is in 71-75F bracket
  Market price: $0.55 (implying 55%)
  Edge = 0.68 - 0.55 = 0.13 (13%)
  Odds = (1/0.55) - 1 = 0.818
  Full Kelly = 0.13 / 0.818 = 15.9% of bankroll
```

### Why Quarter Kelly

Full Kelly is mathematically optimal for long-run growth but practically dangerous:

| Fraction | Growth Rate | Drawdown Risk | Recovery |
|----------|------------|---------------|----------|
| Full Kelly | Maximum | 33% chance of halving before doubling | Slow, painful |
| Half Kelly | 75% of max | 11% chance of halving | Manageable |
| **Quarter Kelly** | **50% of max** | **~3% chance of halving** | **Very smooth** |

**Use quarter Kelly as default.** The growth rate sacrifice (50% of theoretical max) is
trivial compared to the drawdown protection.

### Practical Implementation

```python
def calculate_position(model_prob, market_price, bankroll,
                       kelly_fraction=0.25, max_position_pct=0.05):
    """
    Calculate position size using fractional Kelly.

    Args:
        model_prob: Your model's probability (0-1)
        market_price: Current contract price (0-1)
        bankroll: Total available capital
        kelly_fraction: 0.25 = quarter Kelly (default)
        max_position_pct: Maximum single position as % of bankroll
    """
    edge = model_prob - market_price
    if edge <= 0:
        return 0  # no edge, no bet

    odds = (1.0 / market_price) - 1.0
    full_kelly = edge / odds
    sized = bankroll * full_kelly * kelly_fraction

    # Hard cap: never risk more than 5% of bankroll on one contract
    max_bet = bankroll * max_position_pct
    return min(sized, max_bet)
```

### When to Skip a Bet

Even with a positive edge, sometimes you should pass:

1. **Edge < 5%.** Your model's estimation error likely exceeds 5%. The "edge" may be
   noise. Skip or use 1/8 Kelly at most.

2. **Edge 5-8%.** Marginal. Use 1/8 Kelly only if you have high confidence in the
   specific forecast (e.g., HRRR has been tracking well for this station this week).

3. **Edge 8-15%.** Standard zone. Use quarter Kelly.

4. **Edge > 15%.** Either a genuine opportunity or your model is wrong. Double-check
   the forecast against NWS observations and multiple models before going to half Kelly.

5. **Correlated bets.** If you have positions in adjacent temperature brackets
   (e.g., 71-75 and 76-80 for the same city), they are NOT independent bets. Reduce
   total city exposure to quarter Kelly of the combined edge, not quarter Kelly on each.

6. **Low liquidity.** If the spread is > $0.10, your effective edge after crossing the
   spread may be much smaller. Recalculate edge net of the spread, or use limit orders
   and accept the fill risk.

7. **Near settlement with high certainty.** If the daily high has clearly been reached
   (e.g., 8 PM, temp dropping, clear skies), the market should be pricing the correct
   bracket at $0.90+. The edge is real but the payoff is tiny. Skip unless the market
   is dramatically mispriced.

### Bankroll Management

- **Starting bankroll:** Keep it separate from other Kalshi trading. Weather is its
  own strategy with its own variance profile.
- **Drawdown stop:** If bankroll drops 25% from peak, pause for 48 hours and review
  model calibration. Check: is the model systematically over- or under-predicting?
- **Profit taking:** Withdraw 50% of profits monthly to lock in gains. Compound the
  remaining 50%.
- **Record keeping:** Log every trade with: model_prob, market_price, edge, kelly_size,
  actual_result. This is essential for model calibration.

---

## 8. Architecture Reference

### Minimal Bot Components

```
kalshiweather/
  scan.py            # Main scanner: fetch weather, compute probabilities,
                     #   compare to market, detect edges
  trade.py           # Execute trades via Kalshi API (REST)
  models.py          # Ensemble probability distribution calculation
  nws.py             # NWS data fetcher (DSM, hourly obs, CLI)
  kalshi_ws.py       # WebSocket client for real-time Kalshi prices
  kelly.py           # Position sizing
  config.py          # API keys, station mappings, thresholds
  state.json         # Current positions, bankroll, trade log
  STRATEGY.md        # This file
```

### Data Flow

```
Open-Meteo (GFS/HRRR) ----+
                           |
NWS API (obs/DSM/CLI) ----+---> scan.py ---> edge? ---> trade.py ---> Kalshi API
                           |                    |
Kalshi WebSocket ----------+              kelly.py (sizing)
(real-time prices)
```

### Key API Endpoints

**Kalshi:**
- `GET /markets?event_ticker=NHIGH-{date}-{city}` -- list temperature bracket contracts
- `POST /portfolio/orders` -- place order
- `WebSocket wss://api.elections.kalshi.com/trade-api/ws/v2` -- real-time prices

**Open-Meteo:**
- `GET https://ensemble-api.open-meteo.com/v1/ensemble` -- GFS ensemble
- `GET https://api.open-meteo.com/v1/gfs` -- GFS deterministic + HRRR

**NWS:**
- `GET https://api.weather.gov/stations/{station}/observations/latest` -- latest obs
- `GET https://api.weather.gov/stations/{station}/observations` -- observation history

---

## Quick Reference Card

```
DAILY ROUTINE (all times ET):

10:30 PM  GFS 00Z available. Run ensemble scan for tomorrow. Place initial orders.
 4:30 AM  GFS 06Z available. Update ensemble. Adjust orders if forecast shifted.
 6-9 AM   PRIME WINDOW. HRRR updates hourly. Market hasn't reacted. Hunt edges.
10:30 AM  GFS 12Z available. Final model update before afternoon high.
12-3 PM   Monitor HRRR vs market. Observe actual temp vs forecast.
 3-6 PM   Observational trading. High usually reached. Sell overpriced upper brackets.
 4:30 PM  GFS 18Z available. Start analyzing NEXT day's markets.
 Evening   Close today's positions. Set up tomorrow.

KEY RULES:
- Use quarter Kelly, always
- Edge < 5%? Skip
- Pull orders before DSM release windows
- Auto-approve edges > 15% to save LLM tokens
- Log everything for model calibration
```

---

## Sources

- [Kalshi API Rate Limits](https://docs.kalshi.com/getting_started/rate_limits)
- [Kalshi WebSocket Quick Start](https://docs.kalshi.com/getting_started/quick_start_websockets)
- [Kalshi Weather Markets Help](https://help.kalshi.com/markets/popular-markets/weather-markets)
- [Open-Meteo Ensemble API](https://open-meteo.com/en/docs/ensemble-api)
- [Open-Meteo GFS & HRRR API](https://open-meteo.com/en/docs/gfs-api)
- [Open-Meteo Pricing / Rate Limits](https://open-meteo.com/en/pricing)
- [Open-Meteo Model Update Status](https://open-meteo.com/en/docs/model-updates)
- [Wethr.net Trading Guide](https://wethr.net/edu/trading-guide)
- [Wethr.net Market Bots Guide](https://wethr.net/edu/market-bots)
- [Wethr.net NWS Data Guide](https://wethr.net/edu/nws-data-guide)
- [Weather Bot (ensemble + Kelly example)](https://github.com/suislanchez/polymarket-kalshi-weather-bot)
- [Kelly Criterion - Wikipedia](https://en.wikipedia.org/wiki/Kelly_criterion)
- [Fractional Kelly Discussion (Harry Crane)](https://harrycrane.substack.com/p/two-arguments-for-fractional-kelly)
- [NOAA HRRR Documentation](https://rapidrefresh.noaa.gov/hrrr/)
- [OpenClaw Token Optimization](https://github.com/wassupjay/OpenClaw-Token-Optimization)
