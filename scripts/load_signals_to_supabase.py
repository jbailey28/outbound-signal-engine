#!/usr/bin/env python3
"""Load a reviewed signals CSV into Supabase (account_signals + raw_site_fetches).

Run AFTER reviewing the signals CSV from detect_signals.py.

Usage:
    # validate without writing
    python scripts/load_signals_to_supabase.py data/output/signals_tier2__<stamp>.csv --dry-run

    # load (upserts one current signal per account; appends fetch audit rows)
    python scripts/load_signals_to_supabase.py data/output/signals_tier2__<stamp>.csv

If a sibling "<name>__fetches.csv" exists, its rows are loaded as the audit trail.
Needs SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY in .env.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from outbound_signal_engine.supabase_loader import load_signals, make_client  # noqa: E402


def _read_csv(path: Path) -> list[dict]:
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("signals_csv", help="path to the reviewed signals CSV")
    ap.add_argument("--dry-run", action="store_true", help="validate only; no DB writes")
    args = ap.parse_args()

    signals_path = Path(args.signals_csv)
    if not signals_path.exists():
        print(f"error: not found: {signals_path}", file=sys.stderr)
        return 1

    rows = _read_csv(signals_path)
    fetches_path = signals_path.with_name(signals_path.stem + "__fetches.csv")
    fetch_rows = _read_csv(fetches_path) if fetches_path.exists() else []

    linkable = [r for r in rows if r.get("account_id")]
    print(f"  signals rows   : {len(rows)} ({len(linkable)} linked to an account)")
    print(f"  fetch rows     : {len(fetch_rows)}")

    if args.dry_run:
        missing = len(rows) - len(linkable)
        print(f"\n  dry-run: {missing} rows have no account_id and would be skipped.")
        print("  nothing written.")
        return 0

    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("error: set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env", file=sys.stderr)
        return 1

    client = make_client(url, key)
    result = load_signals(client, rows, fetch_rows)
    print(f"\n  signals upserted : {result['signals_upserted']}")
    print(f"  fetches inserted : {result['fetches_inserted']}")
    print("  done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
