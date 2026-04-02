#!/usr/bin/env bash
# Cron wrapper for kalshi weather auto-trade / auto-settle.
export PATH="$HOME/.local/bin:$PATH"
# Usage (crontab -e):
#   0 10 * * * /path/to/scripts/cron.sh auto            # 6:00 AM EDT (10:00 UTC)
#   0 12 * * * /path/to/scripts/cron.sh auto            # 8:00 AM EDT (12:00 UTC)
#   30 14 * * * /path/to/scripts/cron.sh auto           # 10:30 AM EDT (14:30 UTC)
#   30 15 * * * /path/to/scripts/cron.sh auto-settle    # 11:30 AM EDT (15:30 UTC)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$HOME/.openclaw/kalshi-weather"
mkdir -p "$LOG_DIR"

# Source env vars if .env exists alongside the script or in repo root
ENV_FILE="${SCRIPT_DIR}/../.env"
if [ -f "$ENV_FILE" ]; then
    set -a && source "$ENV_FILE" && set +a
fi

echo "--- $(date -u '+%Y-%m-%dT%H:%M:%S') --- $* ---" >> "$LOG_DIR/cron.log"
uv run "$SCRIPT_DIR/kalshi.py" "$@" 2>&1 | tee -a "$LOG_DIR/cron.log"
