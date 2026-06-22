#!/bin/bash
# Wrapper for the scheduler (macOS launchd / cron). Resolves the project root
# from this script's own location, then runs the daily pipeline with the venv
# Python, logging everything to logs/daily.log.
cd "$(dirname "$0")/.." || exit 1
mkdir -p logs

# One-time pause: don't auto-run before this date (YYYY-MM-DD). First run 2026-06-24
# (Wed). Harmless no-op once the date passes — safe to leave or clear. Manual
# `python scripts/daily.py` runs are NOT affected by this guard.
SKIP_UNTIL="2026-06-24"
TODAY="$(date +%F)"
if [[ "$TODAY" < "$SKIP_UNTIL" ]]; then
  echo "[$(date)] scheduled run skipped ($TODAY before $SKIP_UNTIL)" >> logs/daily.log
  exit 0
fi

{
  echo ""
  echo "===== run: $(date) ====="
  ./.venv/bin/python scripts/daily.py
} >> logs/daily.log 2>&1
