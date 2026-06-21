#!/usr/bin/env python3
"""Load reviewed import artifacts into Supabase.

Run this AFTER you've reviewed the clean CSV. It reads the clean/raw/manifest
trio for one batch and writes them to Supabase.

Usage:
    # validate the artifacts without touching the database
    python scripts/load_to_supabase.py data/output/open_accounts__7bf2070f --dry-run

    # load for real (needs SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY in .env)
    python scripts/load_to_supabase.py data/output/open_accounts__7bf2070f

    # re-import a file that was already loaded
    python scripts/load_to_supabase.py data/output/open_accounts__7bf2070f --force

The PREFIX is the shared stem of the three output files, i.e. the part before
"__manifest.json" / "__accounts_clean.csv" / "__raw_rows.csv".
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from outbound_signal_engine.supabase_loader import discover_artifacts, load  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("prefix", help="shared output prefix, e.g. data/output/<file>__<hash8>")
    ap.add_argument("--dry-run", action="store_true",
                    help="validate artifacts and report, without writing to Supabase")
    ap.add_argument("--force", action="store_true",
                    help="re-import even if this file's hash was already loaded")
    args = ap.parse_args()

    try:
        artifacts = discover_artifacts(args.prefix)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    m = artifacts.manifest
    print("  artifacts")
    print("  " + "-" * 40)
    print(f"  source file   : {m['source_filename']}")
    print(f"  file sha256    : {m['file_sha256'][:12]}…")
    print(f"  raw rows       : {len(artifacts.raw_rows)}")
    print(f"  clean accounts : {len(artifacts.clean_rows)}")

    if args.dry_run:
        # surface a couple of sanity checks a reviewer cares about
        missing_key = [r for r in artifacts.clean_rows if not r.get("dedup_key")]
        dup_keys = _duplicate_keys(artifacts.clean_rows)
        print("\n  dry-run checks")
        print("  " + "-" * 40)
        print(f"  rows missing dedup_key : {len(missing_key)}")
        print(f"  duplicate dedup_keys   : {len(dup_keys)}")
        if dup_keys:
            print(f"    e.g. {dup_keys[:3]}")
        print("\n  dry run only — nothing written to Supabase.")
        return 0 if not missing_key and not dup_keys else 2

    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print(
            "error: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env\n"
            "       (copy .env.example to .env and fill them in).",
            file=sys.stderr,
        )
        return 1

    print("\n  loading to Supabase ...")
    result = load(artifacts, url=url, service_role_key=key, force=args.force)
    if result.get("skipped"):
        print(f"  skipped: {result['reason']}")
        return 0
    print(f"  batch_id            : {result['batch_id']}")
    print(f"  raw rows inserted   : {result['raw_rows_inserted']}")
    print(f"  accounts upserted   : {result['accounts_upserted']}")
    print("  done.")
    return 0


def _duplicate_keys(rows) -> list[str]:
    seen, dups = set(), []
    for r in rows:
        k = r.get("dedup_key")
        if k in seen:
            dups.append(k)
        seen.add(k)
    return dups


if __name__ == "__main__":
    raise SystemExit(main())
