"""A simple local ledger of accounts already surfaced for outreach.

Solves "the bot keeps giving me the same accounts": once an account has been
drafted/posted, its id is recorded here and excluded from future runs, so each
run surfaces the NEXT batch of fresh, high-ranked accounts.

Stored as a CSV under data/output/ (gitignored) — no Supabase change needed.
This is the lightweight precursor to a full active/contacted/nurture lifecycle.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_PATH = Path("data/output/contacted.csv")
COLUMNS = ["account_id", "account_name", "contacted_at"]


def load_contacted_ids(path: Path = DEFAULT_PATH) -> set[str]:
    if not path.exists():
        return set()
    with open(path, newline="") as fh:
        return {r["account_id"] for r in csv.DictReader(fh) if r.get("account_id")}


def mark_contacted(rows: list[dict], path: Path = DEFAULT_PATH) -> int:
    """Append newly-surfaced accounts to the ledger (deduped). Returns count added."""
    already = load_contacted_ids(path)
    new = [r for r in rows if r.get("account_id") and r["account_id"] not in already]
    if not new:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    stamp = datetime.now(timezone.utc).isoformat()
    with open(path, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        if write_header:
            w.writeheader()
        for r in new:
            w.writerow({"account_id": r["account_id"],
                        "account_name": r.get("account_name", ""),
                        "contacted_at": stamp})
    return len(new)


def reset_contacted(path: Path = DEFAULT_PATH) -> bool:
    """Clear the ledger (start the rotation over). Returns True if a file was removed."""
    if path.exists():
        path.unlink()
        return True
    return False
