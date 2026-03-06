#!/bin/bash
# Run the trading bot pipeline and export dashboard data.
# Called by cron every 30 min during market hours.
set -euo pipefail

BOT_DIR="/home/andres-hofmann/Desktop/Cilantro/trading-bot"
VENV="$BOT_DIR/venv/bin/python3"
LOG="$BOT_DIR/logs/bot-run.log"

mkdir -p "$BOT_DIR/logs"

echo "=== Bot run at $(date -u) ===" >> "$LOG"

# Run the bot
$VENV "$BOT_DIR/scripts/run_bot.py" >> "$LOG" 2>&1

# Export dashboard data
$VENV "$BOT_DIR/scripts/export_dashboard_data.py" >> "$LOG" 2>&1

echo "=== Done at $(date -u) ===" >> "$LOG"
