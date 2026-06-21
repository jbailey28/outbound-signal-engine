#!/usr/bin/env python3
"""Detect recent triggers per account and add a timing bonus to the score (M3).

For each target account, searches Google News (broad + trigger-targeted),
classifies headlines into trigger types, scores them by type and recency, and
computes a trigger_score. total_score = fit_score + trigger_score, so a
high-opportunity account with fresh news rises to the top of the daily list.

By default it scans only high-opportunity accounts (fit_score >= 70: greenfield
+ non-Impact), where triggers actually break ties. Use --all for everyone.

Usage:
    python scripts/detect_triggers.py                 # scan high-opportunity, write CSV
    python scripts/detect_triggers.py --all --load    # everyone, upsert results
    python scripts/detect_triggers.py --top 5

Needs SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY in .env.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from outbound_signal_engine.news import GoogleNewsRSS  # noqa: E402
from outbound_signal_engine.scoring import score_account as fit_score_for  # noqa: E402
from outbound_signal_engine.supabase_loader import (  # noqa: E402
    fetch_accounts_with_signals,
    load_scores,
    load_triggers,
    make_client,
)
from outbound_signal_engine.triggers import score_account as score_triggers  # noqa: E402
from outbound_signal_engine.web import make_session  # noqa: E402

COLUMNS = [
    "account_id", "account_name", "domain", "fit_score", "trigger_score",
    "total_score", "top_trigger_type", "top_trigger", "all_trigger_types",
]


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--all", action="store_true", help="scan every account (default: fit>=70)")
    ap.add_argument("--min-fit", type=int, default=70, help="min fit_score to scan (default 70)")
    ap.add_argument("--limit", type=int, default=0, help="cap accounts scanned (testing)")
    ap.add_argument("--load", action="store_true", help="upsert triggers + updated scores")
    ap.add_argument("--top", type=int, default=10, help="how many to print")
    args = ap.parse_args()

    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("error: set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env", file=sys.stderr)
        return 1

    client = make_client(url, key)
    accounts = fetch_accounts_with_signals(client)

    # recompute fit + segment so we don't depend on account_scores being current
    enriched = []
    for a in accounts:
        sc = fit_score_for(account_id=a["id"], account_name=a["account_name"],
                           has_program=a["has_program"], platform=a["platform"])
        enriched.append((a, sc))

    targets = [(a, sc) for a, sc in enriched if args.all or sc.fit_score >= args.min_fit]
    if args.limit:
        targets = targets[:args.limit]
    print(f"scanning {len(targets)} of {len(accounts)} accounts for triggers "
          f"({'all' if args.all else f'fit>={args.min_fit}'}) ...")

    now = datetime.now(timezone.utc)
    results = []        # (account, score_obj, trigger_score, scored_triggers)
    trigger_rows = []   # for account_triggers

    def work(item):
        a, sc = item
        source = GoogleNewsRSS(session=make_session())
        articles = source.search(a["account_name"], limit=10)
        tscore, scored = score_triggers(articles, now, company=a["account_name"])
        return a, sc, tscore, scored

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=3) as ex:
        for a, sc, tscore, scored in ex.map(work, targets):
            results.append((a, sc, tscore, scored))
            for st in scored[:5]:
                trigger_rows.append({
                    "account_id": a["id"],
                    "trigger_type": st.trigger_type,
                    "title": st.title,
                    "url": st.url,
                    "published_at": st.published_at.isoformat() if st.published_at else None,
                    "source": st.source,
                    "score": st.score,
                })

    # rank by total_score (fit + trigger)
    results.sort(key=lambda r: (-(r[1].fit_score + r[2]), r[0]["account_name"].lower()))

    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    out_path = Path("data/output") / f"triggers__{stamp}.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for a, sc, tscore, scored in results:
            top = scored[0] if scored else None
            w.writerow({
                "account_id": a["id"], "account_name": a["account_name"],
                "domain": a.get("domain") or "", "fit_score": sc.fit_score,
                "trigger_score": tscore, "total_score": sc.fit_score + tscore,
                "top_trigger_type": top.trigger_type if top else "",
                "top_trigger": top.title if top else "",
                "all_trigger_types": ",".join(sorted({s.trigger_type for s in scored})),
            })

    with_trig = [r for r in results if r[2] > 0]
    print(f"\n  accounts with a fresh trigger: {len(with_trig)} of {len(results)}")
    print(f"\n  top {args.top} by total score (fit + trigger)")
    print("  " + "-" * 56)
    for a, sc, tscore, scored in results[:args.top]:
        tag = f"+{tscore} {scored[0].trigger_type}" if scored else "—"
        print(f"  [{sc.fit_score + tscore:3}] {a['account_name'][:26]:28} fit {sc.fit_score:3} {tag}")
        if scored:
            print(f"        ↳ {scored[0].title[:70]}")
    print(f"\n  review -> {out_path}")

    if args.load:
        load_triggers(client, trigger_rows)
        payload = [{
            "account_id": sc.account_id, "segment": sc.segment,
            "fit_score": sc.fit_score, "trigger_score": tscore,
            "total_score": sc.fit_score + tscore, "needs_review": sc.needs_review,
            "reasons": sc.reasons,
        } for a, sc, tscore, scored in results]
        load_scores(client, payload)
        print(f"  loaded -> {len(trigger_rows)} trigger rows + {len(payload)} updated scores")
    else:
        print("  (run with --load to store triggers and update scores)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
