#!/usr/bin/env python3
"""Detect affiliate/partner-program signals for accounts (Tier 1).

Reads accounts from Supabase, derives a platform signal from the Competitors
column (no network calls), and writes a review CSV. Tier-2 website scraping is a
separate step; this script flags which accounts need it.

Usage:
    python scripts/detect_signals.py                 # all accounts
    python scripts/detect_signals.py --out data/output/signals.csv

Needs SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY in .env. Writes no DB rows —
review the CSV first, then load (loader added in a later increment).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from outbound_signal_engine.signals import classify_from_competitor  # noqa: E402
from outbound_signal_engine.supabase_loader import fetch_accounts, make_client  # noqa: E402

COLUMNS = [
    "account_id", "account_name", "domain",
    "has_program", "platform", "source", "confidence", "needs_scrape", "evidence",
]


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--out", default=None, help="output CSV path")
    args = ap.parse_args()

    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("error: set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env", file=sys.stderr)
        return 1

    client = make_client(url, key)
    accounts = fetch_accounts(client)
    print(f"read {len(accounts)} accounts from Supabase")

    signals = [
        classify_from_competitor(
            a.get("competitors"),
            account_id=a["id"],
            account_name=a["account_name"],
            domain=a.get("domain"),
        )
        for a in accounts
    ]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = Path(args.out) if args.out else Path("data/output") / f"signals_tier1__{stamp}.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for s in signals:
            w.writerow({
                "account_id": s.account_id,
                "account_name": s.account_name,
                "domain": s.domain or "",
                "has_program": "" if s.has_program is None else s.has_program,
                "platform": s.platform,
                "source": s.source,
                "confidence": s.confidence,
                "needs_scrape": s.needs_scrape,
                "evidence": json.dumps(s.evidence),
            })

    # summary
    resolved = [s for s in signals if s.has_program is True]
    need = [s for s in signals if s.needs_scrape]
    by_platform = Counter(s.platform for s in resolved)

    print("\n  Tier-1 summary")
    print("  " + "-" * 40)
    print(f"  accounts              : {len(signals)}")
    print(f"  resolved (has program): {len(resolved)}  ({len(resolved)*100//max(len(signals),1)}%)")
    print(f"  need Tier-2 scrape    : {len(need)}")
    print("\n  platforms found")
    print("  " + "-" * 40)
    for plat, n in by_platform.most_common():
        print(f"  {n:3}  {plat}")
    print(f"\n  review -> {out_path}")
    print("  next: Tier-2 website scrape for the accounts flagged needs_scrape.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
