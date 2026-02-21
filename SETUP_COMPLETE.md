# Kalshi Weather Trading Bot - SETUP COMPLETE ✅

**Setup Date:** 2026-02-21 11:57 EST  
**Status:** LIVE (Paper Trading Mode)  
**Account Balance:** $745.00 cash + $255.00 in trades = $1000.00 equity

---

## 📊 CURRENT POSITIONS (7 trades placed)

| Ticker | Side | Contracts | Entry Price | Cost | Edge % |
|--------|------|-----------|-------------|------|--------|
| KXHIGHLAX-26FEB21-T73 | YES | 1300 | 1¢ | $13.00 | +545% |
| KXHIGHNY-26FEB21-T43 | NO | 146 | 32¢ | $46.72 | +212% |
| KXHIGHCHI-26FEB22-T35 | YES | 266 | 3¢ | $7.98 | +115% |
| KXHIGHCHI-26FEB21-T35 | NO | 71 | 66¢ | $46.86 | +42% |
| KXHIGHNY-26FEB22-T38 | YES | 73 | 64¢ | $46.72 | +41% |
| KXHIGHLAX-26FEB22-T74 | NO | 60 | 78¢ | $46.80 | +28% |
| KXHIGHNY-26FEB21-T50 | NO | 51 | 92¢ | $46.92 | +9% |

**Total Deployed:** $255.00 (25.5% of account)  
**Average Edge:** +142% across all positions

---

## ⚙️ CONFIGURATION

### API Credentials
- **API Key ID:** a56f7ecc-cf08-48da-850c-522f0bce553f
- **Private Key:** /home/morpheus/Hackstuff/kalshiweather/key.txt
- **Environment:** demo (paper trading)
- **Config File:** /home/morpheus/Hackstuff/kalshiweather/.env

### Workflow Script
- **Path:** /home/morpheus/Hackstuff/kalshiweather/kalshi_workflow.sh
- **Permissions:** Executable (chmod +x)
- **Function:** Auto-scan for edges, execute trades >= 15% edge

---

## 📅 CRON SCHEDULE (5 jobs)

All times Eastern Time (America/New_York):

| Time | Job ID | Purpose |
|------|--------|---------|
| 22:30 (10:30 PM) | 5ff7daae-c2df-44cd-bb04-2dc311800be9 | Evening scan (GFS 00Z) |
| 04:30 (4:30 AM) | 1a186fd6-ad95-4a20-b5f7-5d3032036698 | Early morning (GFS 06Z) |
| 07:00 (7:00 AM) | 03edd16b-9535-4451-bba4-76b4bdaa2abb | **PRIME WINDOW** + settlement |
| 10:30 (10:30 AM) | 2ee24e7d-b099-4819-81ea-66280d6f94d1 | Midday (GFS 12Z) |
| 16:30 (4:30 PM) | e3a7bf1c-7b2c-40f4-a164-b8fd591d2f00 | Afternoon (GFS 18Z) |

### Next Runs:
- **Today 16:30 ET** (4:30 PM) - Afternoon scan
- **Today 22:30 ET** (10:30 PM) - Evening scan
- **Tomorrow 04:30 ET** (4:30 AM) - Early morning scan
- **Tomorrow 07:00 ET** (7:00 AM) - **PRIME WINDOW**

---

## 🤖 AUTOMATION RULES

### Auto-Execute Conditions:
- **Edge >= 15%** → Execute immediately without confirmation
- **Edge 8-15%** → Execute but log as standard-confidence
- **Edge < 8%** → Skip (model error likely exceeds edge)

### Position Sizing:
- **Kelly Fraction:** 0.25 (quarter-Kelly)
- **Max Position:** 5% of account balance
- **Max Same-City-Same-Day:** 3 positions

### Risk Management:
- If balance drops 25% from peak → pause 48 hours
- Always use --json flag for programmatic parsing
- Spread > 10¢ → recalculate edge or use limit orders

---

## 📋 MANUAL COMMANDS

### Check Status:
```bash
cd /home/morpheus/Hackstuff/kalshiweather
KALSHI_API_KEY_ID="a56f7ecc-cf08-48da-850c-522f0bce553f" \
KALSHI_PRIVATE_KEY_PATH="/home/morpheus/Hackstuff/kalshiweather/key.txt" \
KALSHI_ENV="demo" \
uv run scripts/kalshi.py --json positions
```

### Scan for Edges:
```bash
KALSHI_API_KEY_ID="a56f7ecc-cf08-48da-850c-522f0bce553f" \
KALSHI_PRIVATE_KEY_PATH="/home/morpheus/Hackstuff/kalshiweather/key.txt" \
KALSHI_ENV="demo" \
uv run scripts/kalshi.py --json scan
```

### Run Workflow Manually:
```bash
/home/morpheus/Hackstuff/kalshiweather/kalshi_workflow.sh
```

### Settle a Position (after event date):
```bash
uv run scripts/kalshi.py settle TICKER won   # if your bet was correct
uv run scripts/kalshi.py settle TICKER lost  # if your bet was wrong
```

---

## 🎯 WHAT HAPPENS NEXT

1. **Cron jobs will fire automatically** at scheduled times
2. **Workflow will:**
   - Check current positions
   - Scan all 6 cities for edges
   - Auto-execute any edge >= 15%
   - Log results to `/tmp/kalshi_*.json`
3. **System events will ping main session** with results
4. **Settlement:** You'll be notified when positions need settling

---

## 🚀 READY TO PRINT MONEY

**Paper trading is LIVE.** The bot will:
- Monitor GFS ensemble forecasts
- Find mispriced markets
- Execute high-edge trades automatically
- Track P&L

**Next milestone:** Switch to `KALSHI_ENV=prod` for real money (after proving profitability in paper mode)

🤙 LET'S FUCKING GO
