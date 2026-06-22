"""Load reviewed import artifacts into Supabase.

Reads the three files an import produces (clean CSV, raw CSV, manifest JSON) and
writes them to the schema in db/schema.sql:

    import_batches   <- one row, from the manifest
    raw_account_rows <- every row from the raw CSV (audit)
    accounts         <- upsert from the clean CSV, keyed on dedup_key

The loader deliberately consumes the *reviewed* CSVs rather than re-parsing the
PDF, so nothing reaches the database that a human hasn't seen.

Requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in the environment (.env).
The service-role key is used so the import can write past row-level security;
keep it server-side only.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ACCOUNT_COLUMNS = [
    "account_name", "website", "domain", "name_key", "dedup_key",
    "competitors", "industry", "sub_industry",
]
RAW_COLUMNS = [
    "row_index", "page_number",
    "account_name", "website", "competitors", "industry", "sub_industry",
]


@dataclass
class ImportArtifacts:
    """The three files produced by one import batch."""

    manifest: dict[str, Any]
    clean_rows: list[dict[str, str]]
    raw_rows: list[dict[str, str]]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def discover_artifacts(prefix: str) -> ImportArtifacts:
    """Load the clean/raw/manifest trio sharing an output prefix.

    `prefix` is the path stem, e.g. data/output/open_accounts__7bf2070f
    """
    base = Path(prefix)
    manifest_path = base.with_name(base.name + "__manifest.json")
    clean_path = base.with_name(base.name + "__accounts_clean.csv")
    raw_path = base.with_name(base.name + "__raw_rows.csv")

    for p in (manifest_path, clean_path, raw_path):
        if not p.exists():
            raise FileNotFoundError(f"expected artifact not found: {p}")

    return ImportArtifacts(
        manifest=json.loads(manifest_path.read_text()),
        clean_rows=_read_csv(clean_path),
        raw_rows=_read_csv(raw_path),
    )


def _empty_to_none(row: dict[str, str], columns: list[str]) -> dict[str, Any]:
    """Project a CSV row to the given columns, turning '' into None."""
    return {c: (row.get(c) or None) for c in columns}


def load(
    artifacts: ImportArtifacts,
    *,
    url: str,
    service_role_key: str,
    force: bool = False,
) -> dict[str, Any]:
    """Write the artifacts to Supabase. Returns a small summary dict.

    Idempotency: if a batch with the same file_sha256 already exists, we skip
    unless `force=True` (which creates a fresh batch and re-upserts accounts).
    """
    from supabase import create_client  # imported lazily so --dry-run needs no dep

    client = create_client(url, service_role_key)
    sha = artifacts.manifest["file_sha256"]

    existing = (
        client.table("import_batches")
        .select("id")
        .eq("file_sha256", sha)
        .execute()
    )
    if existing.data and not force:
        return {
            "skipped": True,
            "reason": f"file_sha256 {sha[:8]} already imported "
                      f"(batch {existing.data[0]['id']}). Use force=True to re-import.",
        }

    # 1. import_batches
    m = artifacts.manifest
    batch = (
        client.table("import_batches")
        .insert({
            "source_filename": m["source_filename"],
            "file_sha256": sha,
            "raw_row_count": m.get("raw_row_count", len(artifacts.raw_rows)),
            "clean_row_count": m.get("clean_row_count", len(artifacts.clean_rows)),
            "status": "imported",
        })
        .execute()
    )
    batch_id = batch.data[0]["id"]

    # 2. raw_account_rows (chunked)
    raw_payload = [
        {**_empty_to_none(r, RAW_COLUMNS), "batch_id": batch_id}
        for r in artifacts.raw_rows
    ]
    _chunked_insert(client, "raw_account_rows", raw_payload)

    # 3. accounts upsert on dedup_key. We set last_seen_batch here but NOT
    #    first_seen_batch, so existing accounts keep their original first_seen.
    acct_payload = [
        {**_empty_to_none(r, ACCOUNT_COLUMNS), "last_seen_batch": batch_id}
        for r in artifacts.clean_rows
    ]
    _chunked_upsert(client, "accounts", acct_payload, on_conflict="dedup_key")

    # backfill first_seen_batch for brand-new accounts only
    client.table("accounts").update({"first_seen_batch": batch_id}).is_(
        "first_seen_batch", "null"
    ).execute()

    # 4. mark batch loaded
    client.table("import_batches").update({"status": "loaded"}).eq(
        "id", batch_id
    ).execute()

    return {
        "skipped": False,
        "batch_id": batch_id,
        "raw_rows_inserted": len(raw_payload),
        "accounts_upserted": len(acct_payload),
    }


def make_client(url: str, service_role_key: str):
    """Create a Supabase client (service-role key bypasses RLS)."""
    from supabase import create_client

    return create_client(url, service_role_key)


def fetch_accounts(client, columns: str = "id,account_name,domain,website,competitors") -> list[dict]:
    """Read all accounts, paging past PostgREST's default 1000-row cap."""
    out: list[dict] = []
    page, size = 0, 1000
    while True:
        rows = (
            client.table("accounts")
            .select(columns)
            .range(page * size, page * size + size - 1)
            .execute()
            .data
        )
        out.extend(rows)
        if len(rows) < size:
            return out
        page += 1


def load_signals(client, signal_rows: list[dict], fetch_rows: list[dict] | None = None) -> dict:
    """Upsert account_signals (one current per account) + append fetch audit.

    `signal_rows` come from the reviewed signals CSV; evidence is a JSON string
    there and is parsed back to a dict for the jsonb column. has_program '' -> None.
    """
    import json as _json

    payload = []
    for r in signal_rows:
        if not r.get("account_id"):
            continue  # can't link a signal without an account
        hp = r.get("has_program", "")
        has_program = None if hp in ("", None) else (hp in ("True", "true", True))
        ev = r.get("evidence") or "{}"
        payload.append({
            "account_id": r["account_id"],
            "signal_type": "affiliate_program",
            "has_program": has_program,
            "platform": r.get("platform") or "unknown",
            "source": r["source"],
            "confidence": r.get("confidence") or "low",
            "evidence": _json.loads(ev) if isinstance(ev, str) else ev,
        })

    _chunked_upsert(client, "account_signals", payload,
                    on_conflict="account_id,signal_type")

    inserted_fetches = 0
    if fetch_rows:
        fpayload = []
        for f in fetch_rows:
            if not f.get("account_id"):
                continue
            fpayload.append({
                "account_id": f["account_id"],
                "url": f.get("url"),
                "http_status": int(f["http_status"]) if str(f.get("http_status", "")).isdigit() else None,
                "matched": {"note": f.get("note", "")},
                "error": f.get("error") or None,
            })
        _chunked_insert(client, "raw_site_fetches", fpayload)
        inserted_fetches = len(fpayload)

    return {"signals_upserted": len(payload), "fetches_inserted": inserted_fetches}


def fetch_accounts_with_signals(client) -> list[dict]:
    """Accounts joined to their affiliate_program signal (left join)."""
    rows = (
        client.table("accounts")
        .select("id,account_name,domain,account_signals(has_program,platform,signal_type)")
        .execute()
        .data
    )
    out = []
    for a in rows:
        sig = next(
            (s for s in (a.get("account_signals") or [])
             if s.get("signal_type") == "affiliate_program"),
            None,
        )
        out.append({
            "id": a["id"],
            "account_name": a["account_name"],
            "domain": a.get("domain"),
            "has_program": sig.get("has_program") if sig else None,
            "platform": sig.get("platform") if sig else None,
        })
    return out


def fetch_prospects_for_drafts(client) -> list[dict]:
    """Accounts enriched with segment/score + their top trigger type, ranked."""
    accts = (
        client.table("accounts")
        .select("id,account_name,domain,website,industry,sub_industry,"
                "account_scores(segment,total_score)")
        .execute().data
    )
    trigs = client.table("account_triggers").select(
        "account_id,trigger_type,title,score").execute().data
    top: dict[str, dict] = {}
    for t in trigs:
        aid = t["account_id"]
        if aid not in top or (t.get("score") or 0) > (top[aid].get("score") or 0):
            top[aid] = t

    out = []
    for a in accts:
        scores = a.get("account_scores") or []
        sc = scores[0] if scores else {}
        out.append({
            "account_id": a["id"],
            "account_name": a["account_name"],
            "domain": a.get("domain"),
            "website": a.get("website"),
            "industry": a.get("industry"),
            "sub_industry": a.get("sub_industry"),
            "segment": sc.get("segment", "unknown"),
            "total_score": sc.get("total_score", 0) or 0,
            "top_trigger_type": top.get(a["id"], {}).get("trigger_type"),
            "top_trigger_title": top.get(a["id"], {}).get("title"),
        })
    out.sort(key=lambda r: -r["total_score"])
    return out


def load_scores(client, score_rows: list[dict]) -> dict:
    """Upsert account_scores (one current score per account)."""
    payload = [r for r in score_rows if r.get("account_id")]
    _chunked_upsert(client, "account_scores", payload, on_conflict="account_id")
    return {"scores_upserted": len(payload)}


def load_triggers(client, trigger_rows: list[dict]) -> dict:
    """Replace the trigger set for each scanned account (idempotent refresh).

    Delete-then-insert per account rather than upsert, so a re-run reflects the
    current news snapshot without depending on a partial unique index (which
    PostgREST can't target with ON CONFLICT).
    """
    payload = [r for r in trigger_rows if r.get("account_id") and r.get("url")]
    account_ids = list({r["account_id"] for r in payload})
    for i in range(0, len(account_ids), 100):
        client.table("account_triggers").delete().in_(
            "account_id", account_ids[i:i + 100]
        ).execute()
    if payload:
        _chunked_insert(client, "account_triggers", payload)
    return {"triggers_inserted": len(payload)}


def _chunked_insert(client, table: str, rows: list[dict], size: int = 500) -> None:
    for i in range(0, len(rows), size):
        client.table(table).insert(rows[i:i + size]).execute()


def _chunked_upsert(client, table: str, rows: list[dict], *, on_conflict: str,
                    size: int = 500) -> None:
    for i in range(0, len(rows), size):
        client.table(table).upsert(rows[i:i + size], on_conflict=on_conflict).execute()
