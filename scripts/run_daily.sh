#!/bin/bash
# Wrapper for the scheduler (macOS launchd / cron). Resolves the project root
# from this script's own location, then runs the daily pipeline with the venv
# Python, logging everything to logs/daily.log.
cd "$(dirname "$0")/.." || exit 1
mkdir -p logs
{
  echo ""
  echo "===== run: $(date) ====="
  ./.venv/bin/python scripts/daily.py
} >> logs/daily.log 2>&1
