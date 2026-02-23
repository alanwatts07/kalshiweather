#!/bin/bash
# Kalshi Weather Trading Workflow
# Run this from cron to check positions, scan edges, and trade

cd /home/morpheus/Hackstuff/kalshiweather

# Load env vars
export KALSHI_API_KEY_ID="a56f7ecc-cf08-48da-850c-522f0bce553f"
export KALSHI_PRIVATE_KEY_PATH="/home/morpheus/Hackstuff/kalshiweather/key.txt"
export KALSHI_ENV="demo"

# Log file
LOGFILE="/home/morpheus/Hackstuff/kalshiweather/workflow.log"
TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S %Z")

# Helper function for logging
log() {
    echo "[$TIMESTAMP] $1" | tee -a "$LOGFILE"
}

log "========================================="
log "Kalshi workflow starting..."

# 0. Auto-settle expired positions
log "Auto-settling expired positions..."
uv run scripts/kalshi.py auto-settle 2>&1 | tee -a "$LOGFILE"

# 1. Check current positions
log "Checking positions..."
uv run scripts/kalshi.py --json positions > /tmp/kalshi_positions.json 2>&1
BALANCE=$(uv run scripts/kalshi.py balance 2>&1 | grep -A 1 "Paper Trading Account" | tail -1)
log "Balance: $BALANCE"

# 2. Scan for edges
log "Scanning for edges..."
uv run scripts/kalshi.py --json scan > /tmp/kalshi_scan.json 2>&1

# Extract edges >= 8% from the scan output
EDGES=$(cat /tmp/kalshi_scan.json | grep -A 1000 "^\[" | jq -r '.[] | select(.edge_pct >= 8) | "\(.ticker) \(.side) \(.edge_pct | floor)%"' 2>/dev/null)

if [ -n "$EDGES" ]; then
    log "Found edges >= 8%:"
    echo "$EDGES" | while read line; do log "  $line"; done
    
    # Parse and execute high-confidence trades (edge >= 15%)
    cat /tmp/kalshi_scan.json | grep -A 1000 "^\[" | jq -r '.[] | select(.edge_pct >= 15) | @json' 2>/dev/null | while read -r edge; do
        TICKER=$(echo "$edge" | jq -r '.ticker')
        SIDE=$(echo "$edge" | jq -r '.side')
        PRICE=$(echo "$edge" | jq -r '.market_price')
        SUGGESTED=$(echo "$edge" | jq -r '.suggested_contracts')
        EDGE_PCT=$(echo "$edge" | jq -r '.edge_pct | floor')
        
        # Calculate dollar amount (suggested contracts * price in cents / 100)
        DOLLARS=$(echo "scale=2; ($SUGGESTED * $PRICE) / 100" | bc)
        
        log "AUTO-EXECUTING: $TICKER $SIDE @ ${PRICE}¢ (${EDGE_PCT}% edge, $SUGGESTED contracts = \$$DOLLARS)"
        RESULT=$(uv run scripts/kalshi.py buy "$TICKER" "$SIDE" "$DOLLARS" --price "$PRICE" 2>&1)
        log "Result: $RESULT"
    done
else
    log "No edges found >= 8%"
fi

# 3. Check final balance
log "Final balance:"
uv run scripts/kalshi.py balance 2>&1 | tee -a "$LOGFILE"

log "Workflow complete."
log "========================================="
