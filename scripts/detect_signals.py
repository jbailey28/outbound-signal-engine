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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from outbound_signal_engine.affiliate_scrape import detect_from_website  # noqa: E402
from outbound_signal_engine.signals import classify_from_competitor  # noqa: E402
from outbound_signal_engine.supabase_loader import fetch_accounts, make_client  # noqa: E402
from outbound_signal_engine.web import make_session  # noqa: E402

COLUMNS = [
    "account_id", "account_name", "domain",
    "has_program", "platform", "source", "confidence", "needs_scrape", "evidence",
]
FETCH_COLUMNS = ["account_id", "url", "final_url", "http_status", "error", "note"]


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--out", default=None, help="output CSV path")
    ap.add_argument("--scrape", action="store_true",
                    help="run Tier-2 website scraping on accounts Tier-1 couldn't resolve")
    ap.add_argument("--max-workers", type=int, default=6,
                    help="concurrent fetches for Tier-2 (default 6)")
    ap.add_argument("--limit", type=int, default=0,
                    help="cap how many accounts to scrape (0 = no cap; for testing)")
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

    # ---- Tier 2: scrape the websites Tier-1 couldn't resolve ----
    fetch_rows: list[dict] = []
    if args.scrape:
        to_scrape = [s for s in signals if s.needs_scrape and s.domain]
        if args.limit:
            to_scrape = to_scrape[:args.limit]
        by_id = {id(s): i for i, s in enumerate(signals)}
        print(f"Tier-2: scraping {len(to_scrape)} sites (max_workers={args.max_workers}) ...")

        def _scrape(sig):
            sess = make_session()
            outcome = detect_from_website(
                account_id=sig.account_id, account_name=sig.account_name,
                domain=sig.domain, session=sess,
            )
            return sig, outcome

        with ThreadPoolExecutor(max_workers=args.max_workers) as ex:
            for orig, outcome in ex.map(_scrape, to_scrape):
                outcome.signal.needs_scrape = False
                signals[by_id[id(orig)]] = outcome.signal
                fetch_rows.extend(outcome.fetches)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tier = "tier2" if args.scrape else "tier1"
    out_path = Path(args.out) if args.out else Path("data/output") / f"signals_{tier}__{stamp}.csv"
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

    # write the fetch audit trail when we scraped
    fetch_path = None
    if args.scrape and fetch_rows:
        fetch_path = out_path.with_name(out_path.stem + "__fetches.csv")
        with open(fetch_path, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=FETCH_COLUMNS)
            w.writeheader()
            w.writerows(fetch_rows)

    # summary
    has = [s for s in signals if s.has_program is True]
    no = [s for s in signals if s.has_program is False]
    unknown = [s for s in signals if s.has_program is None]
    need = [s for s in signals if s.needs_scrape]
    by_platform = Counter(s.platform for s in has)

    n = len(signals)
    print(f"\n  {'Tier-2' if args.scrape else 'Tier-1'} summary")
    print("  " + "-" * 40)
    print(f"  accounts              : {n}")
    print(f"  has program           : {len(has)}  ({len(has)*100//max(n,1)}%)")
    print(f"  no program found      : {len(no)}")
    print(f"  unknown               : {len(unknown)}")
    if not args.scrape:
        print(f"  flagged for Tier-2    : {len(need)}")
    print("\n  platforms (where program found)")
    print("  " + "-" * 40)
    for plat, cnt in by_platform.most_common():
        print(f"  {cnt:3}  {plat}")
    print(f"\n  review -> {out_path}")
    if fetch_path:
        print(f"  audit  -> {fetch_path}")
    if not args.scrape:
        print("  next: re-run with --scrape to resolve the flagged accounts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
