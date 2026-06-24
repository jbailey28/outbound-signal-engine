#!/usr/bin/env python3
"""One command for the daily run: refresh triggers, re-rank, draft the top 5,
and post them to Discord. This is what the DigitalOcean cron calls.

Steps:
  1. detect_triggers --load   (fresh news → updated trigger scores)
  2. score_accounts --load    (re-rank with the new triggers)
  3. generate_drafts          (top N → data/output/today/, overwritten daily)
  4. post the drafts to Discord (if DISCORD_WEBHOOK_URL is set)

Usage:
    python scripts/daily.py                      # provider from DRAFT_PROVIDER or claude
    python scripts/daily.py --provider ollama --top 5

Env: SUPABASE_*, a draft provider's creds (ANTHROPIC_API_KEY / Ollama), and
DISCORD_WEBHOOK_URL. Reads DRAFT_PROVIDER as the default provider.
"""

from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from outbound_signal_engine.notify import post_drafts  # noqa: E402

TODAY_DIR = ROOT / "data" / "output" / "today"
PY = sys.executable


def _run(script: str, *script_args: str) -> bool:
    """Run a pipeline script; return True on success, log and continue on failure."""
    cmd = [PY, str(ROOT / "scripts" / script), *script_args]
    print(f"\n$ {' '.join(cmd[1:])}")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print(f"  ! {script} exited {result.returncode} (continuing)", file=sys.stderr)
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provider", default=None, help="template | claude | ollama")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--skip-refresh", action="store_true",
                    help="skip the triggers/score refresh; just draft + post")
    args = ap.parse_args()

    os.chdir(ROOT)  # operate from the project root regardless of launch directory
    load_dotenv(ROOT / ".env")
    provider = args.provider or os.environ.get("DRAFT_PROVIDER") or "claude"

    if not args.skip_refresh:
        _run("detect_triggers.py", "--load")
        _run("score_accounts.py", "--load")

    if not _run("generate_drafts.py", "--top", str(args.top),
                "--provider", provider, "--out-dir", str(TODAY_DIR)):
        print("draft generation failed — nothing to post", file=sys.stderr)
        return 1

    # post to Discord
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    csv_path = TODAY_DIR / "_drafts.csv"
    if not webhook:
        print(f"\nDISCORD_WEBHOOK_URL not set — drafts are in {TODAY_DIR}/ (not posted).")
        return 0
    if not csv_path.exists():
        print("no _drafts.csv produced", file=sys.stderr)
        return 1

    rows = list(csv.DictReader(open(csv_path, newline="")))
    date_str = datetime.now(timezone.utc).strftime("%a %b %-d")
    try:
        n = post_drafts(webhook, date_str, rows)
        print(f"\nposted {n} Discord messages for {len(rows)} drafts.")
    except Exception as e:  # noqa: BLE001
        print(f"Discord post failed: {e}\nDrafts are still in {TODAY_DIR}/", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
