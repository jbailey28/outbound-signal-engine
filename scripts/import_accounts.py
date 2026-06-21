#!/usr/bin/env python3
"""Import a Salesforce Printable-View PDF into clean account CSVs.

Usage:
    python scripts/import_accounts.py path/to/export.pdf
    python scripts/import_accounts.py export.pdf --outdir data/output

Outputs (in --outdir, default data/output/):
    <stem>__<hash8>__accounts_clean.csv   <- review this before loading
    <stem>__<hash8>__raw_rows.csv         <- audit trail of extracted rows
    <stem>__<hash8>__manifest.json        <- batch metadata

This script does NOT write to Supabase. Loading the reviewed CSV is a separate,
explicit step. Nothing leaves your machine.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# allow running as a plain script without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from outbound_signal_engine.accounts import (  # noqa: E402
    accounts_to_dicts,
    build_clean_accounts,
    file_sha256,
    rows_to_raw_dicts,
)
from outbound_signal_engine.config import FIELDS  # noqa: E402
from outbound_signal_engine.pdf_import import extract_rows  # noqa: E402

CLEAN_COLUMNS = [
    "account_name", "website", "domain", "name_key",
    "competitors", "industry", "sub_industry", "dedup_key",
]
RAW_COLUMNS = ["row_index", "page_number", *FIELDS]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", help="path to the Salesforce Printable-View PDF")
    ap.add_argument("--outdir", default="data/output",
                    help="output directory (default: data/output)")
    args = ap.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"error: file not found: {pdf_path}", file=sys.stderr)
        return 1

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"reading {pdf_path} ...")
    sha = file_sha256(str(pdf_path))
    rows = extract_rows(str(pdf_path))

    if not rows:
        print(
            "no rows extracted. The PDF may not contain a recognized table, or the\n"
            "column headers differ from what's configured. Check that this is a\n"
            "Salesforce *Printable View* PDF, then add header aliases in\n"
            "src/outbound_signal_engine/config.py (HEADER_ALIASES).",
            file=sys.stderr,
        )
        return 2

    clean = build_clean_accounts(rows)

    stem = f"{pdf_path.stem}__{sha[:8]}"
    raw_csv = outdir / f"{stem}__raw_rows.csv"
    clean_csv = outdir / f"{stem}__accounts_clean.csv"
    manifest_json = outdir / f"{stem}__manifest.json"

    pd.DataFrame(rows_to_raw_dicts(rows)).reindex(columns=RAW_COLUMNS).to_csv(
        raw_csv, index=False
    )
    pd.DataFrame(accounts_to_dicts(clean)).reindex(columns=CLEAN_COLUMNS).to_csv(
        clean_csv, index=False
    )

    with_domain = sum(1 for a in clean if a.domain)
    manifest = {
        "source_filename": pdf_path.name,
        "file_sha256": sha,
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "raw_row_count": len(rows),
        "clean_row_count": len(clean),
        "accounts_with_domain": with_domain,
        "accounts_without_domain": len(clean) - with_domain,
        "duplicates_collapsed": len(rows) - len(clean),
        "status": "imported",
    }
    manifest_json.write_text(json.dumps(manifest, indent=2))

    print("\n  import summary")
    print("  " + "-" * 40)
    print(f"  rows extracted (raw)   : {len(rows)}")
    print(f"  clean accounts         : {len(clean)}")
    print(f"  duplicates collapsed   : {len(rows) - len(clean)}")
    print(f"  with domain            : {with_domain}")
    print(f"  without domain (name)  : {len(clean) - with_domain}")
    print("\n  outputs")
    print("  " + "-" * 40)
    print(f"  review -> {clean_csv}")
    print(f"  audit  -> {raw_csv}")
    print(f"  batch  -> {manifest_json}")
    print("\n  next: review the clean CSV, then load it into Supabase.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
