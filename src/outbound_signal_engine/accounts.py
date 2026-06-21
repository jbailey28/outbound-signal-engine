"""Turn extracted PDF rows into a clean, deduplicated account book.

Pipeline:
    extract_rows()  ->  build_clean_accounts()  ->  CSVs + manifest

Dedup rule (matches db/schema.sql):
    * primary key  = normalized website domain, when present
    * fallback key = normalized account name, when there is no website
When two rows collapse to the same key, the LATER row wins on non-empty fields
(so a more complete duplicate enriches the earlier one).
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass

from .domains import clean_url, name_key, normalize_domain
from .pdf_import import ExtractedRow


@dataclass
class CleanAccount:
    account_name: str
    website: str | None
    domain: str | None
    name_key: str
    competitors: str | None
    industry: str | None
    sub_industry: str | None
    dedup_key: str  # the key this account was deduped on (audit aid)


def file_sha256(path: str) -> str:
    """Content hash of the source PDF — lets us detect re-imports."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _dedup_key(domain: str | None, nkey: str) -> str:
    return f"domain:{domain}" if domain else f"name:{nkey}"


def _coalesce(existing: str | None, incoming: str | None) -> str | None:
    """Prefer a non-empty incoming value, else keep what we had."""
    incoming = (incoming or "").strip()
    return incoming or existing


def build_clean_accounts(rows: list[ExtractedRow]) -> list[CleanAccount]:
    """Clean + deduplicate extracted rows into the final account list."""
    by_key: dict[str, CleanAccount] = {}

    for row in rows:
        v = row.values
        account_name = (v.get("account_name") or "").strip()
        if not account_name:
            continue

        domain = normalize_domain(v.get("website"))
        website = clean_url(v.get("website"))
        nkey = name_key(account_name)
        key = _dedup_key(domain, nkey)

        candidate = CleanAccount(
            account_name=account_name,
            website=website,
            domain=domain,
            name_key=nkey,
            competitors=(v.get("competitors") or "").strip() or None,
            industry=(v.get("industry") or "").strip() or None,
            sub_industry=(v.get("sub_industry") or "").strip() or None,
            dedup_key=key,
        )

        if key not in by_key:
            by_key[key] = candidate
        else:
            # merge: later row enriches earlier one on empty fields
            existing = by_key[key]
            existing.account_name = existing.account_name or candidate.account_name
            existing.website = _coalesce(existing.website, candidate.website)
            existing.domain = existing.domain or candidate.domain
            existing.competitors = _coalesce(existing.competitors, candidate.competitors)
            existing.industry = _coalesce(existing.industry, candidate.industry)
            existing.sub_industry = _coalesce(existing.sub_industry, candidate.sub_industry)

    return list(by_key.values())


def rows_to_raw_dicts(rows: list[ExtractedRow]) -> list[dict]:
    """Flatten extracted rows for the raw-audit CSV."""
    out = []
    for r in rows:
        d = {
            "row_index": r.row_index,
            "page_number": r.page_number,
            **r.values,
        }
        out.append(d)
    return out


def accounts_to_dicts(accounts: list[CleanAccount]) -> list[dict]:
    return [asdict(a) for a in accounts]
