#!/usr/bin/env python3
"""Score accounts by opportunity and produce a ranked prospect list (Milestone 4).

Reads accounts + their affiliate signal from Supabase, computes an opportunity
score (greenfield > non-Impact platform > on Impact), writes a ranked review
CSV, and optionally upserts the scores back to Supabase.

Usage:
    python scripts/score_accounts.py              # compute + write ranked CSV
    python scripts/score_accounts.py --load       # also upsert into account_scores
    python scripts/score_accounts.py --top 5      # print the daily top 5

Needs SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY in .env.
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

from outbound_signal_engine.scoring import score_account  # noqa: E402
from outbound_signal_engine.supabase_loader import (  # noqa: E402
    fetch_accounts_with_signals,
    load_scores,
    make_client,
)

COLUMNS = [
    "rank", "account_id", "account_name", "domain",
    "segment", "fit_score", "trigger_score", "total_score", "needs_review", "reasons",
]


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--load", action="store_true", help="upsert scores into Supabase")
    ap.add_argument("--top", type=int, default=10, help="how many to print (default 10)")
    ap.add_argument("--out", default=None, help="output CSV path")
    args = ap.parse_args()

    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("error: set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env", file=sys.stderr)
        return 1

    client = make_client(url, key)
    accounts = fetch_accounts_with_signals(client)
    print(f"read {len(accounts)} accounts (with signals) from Supabase")

    scores = [
        score_account(
            account_id=a["id"], account_name=a["account_name"],
            has_program=a["has_program"], platform=a["platform"],
        )
        for a in accounts
    ]
    # rank: highest total first, then name for stable ties
    scores.sort(key=lambda s: (-s.total_score, s.account_name.lower()))

    domain_by_id = {a["id"]: a.get("domain") for a in accounts}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = Path(args.out) if args.out else Path("data/output") / f"ranked_accounts__{stamp}.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for i, s in enumerate(scores, start=1):
            w.writerow({
                "rank": i,
                "account_id": s.account_id,
                "account_name": s.account_name,
                "domain": domain_by_id.get(s.account_id) or "",
                "segment": s.segment,
                "fit_score": s.fit_score,
                "trigger_score": s.trigger_score,
                "total_score": s.total_score,
                "needs_review": s.needs_review,
                "reasons": json.dumps(s.reasons),
            })

    # summary
    by_segment = Counter(s.segment for s in scores)
    print("\n  segments")
    print("  " + "-" * 44)
    for seg in ("greenfield", "non_impact_platform", "unknown", "on_impact"):
        if by_segment.get(seg):
            print(f"  {by_segment[seg]:3}  {seg}")

    print(f"\n  top {args.top} prospects")
    print("  " + "-" * 44)
    for i, s in enumerate(scores[:args.top], start=1):
        dom = domain_by_id.get(s.account_id) or ""
        flag = " (review)" if s.needs_review else ""
        print(f"  {i:2}. [{s.total_score:3}] {s.account_name[:28]:30} {s.segment}{flag}  {dom}")

    print(f"\n  ranked list -> {out_path}")

    if args.load:
        payload = [{
            "account_id": s.account_id,
            "segment": s.segment,
            "fit_score": s.fit_score,
            "trigger_score": s.trigger_score,
            "total_score": s.total_score,
            "needs_review": s.needs_review,
            "reasons": s.reasons,
        } for s in scores]
        result = load_scores(client, payload)
        print(f"  loaded -> account_scores upserted: {result['scores_upserted']}")
    else:
        print("  (run with --load to upsert these scores into Supabase)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
