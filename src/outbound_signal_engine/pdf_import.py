"""Extract account rows from a Salesforce Printable-View PDF.

Salesforce "Printable View" renders a list view as an HTML table, which exports
to PDF as a real table grid. We use pdfplumber's table extraction and then map
the detected header row onto our canonical fields (see config.HEADER_ALIASES).

The parser is defensive on purpose:
  * the header row is located by fuzzy-matching against known aliases, so a
    repeated page header or a leading title row won't break column mapping;
  * tables that span multiple pages are concatenated, re-detecting the header
    on each page (Salesforce repeats it);
  * we always keep the full original row as `raw` JSON so nothing is lost even
    if the column layout shifts.

If a real export doesn't parse cleanly, the fix is almost always to add a header
alias in config.py — not to change this file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import pdfplumber

from .config import FIELDS, HEADER_ALIASES, REQUIRED_FIELDS


@dataclass
class ExtractedRow:
    """One row pulled from the PDF, before cleaning/dedup."""

    row_index: int
    page_number: int
    values: dict[str, str]  # canonical_field -> raw cell text
    raw: dict[str, Any] = field(default_factory=dict)


def _norm_header(text: str | None) -> str:
    """Normalize a header cell for alias matching."""
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", " ", text)  # punctuation -> space
    return re.sub(r"\s+", " ", text).strip()


def _match_header_row(row: list[str | None]) -> dict[int, str] | None:
    """If `row` looks like a header, return {column_index -> canonical_field}.

    Requires at least the account-name column plus one other to be confident
    we found the header and not a data row that happens to contain a keyword.
    """
    normalized = [_norm_header(c) for c in row]
    mapping: dict[int, str] = {}
    for col_idx, cell in enumerate(normalized):
        if not cell:
            continue
        for field_name, aliases in HEADER_ALIASES.items():
            if field_name in mapping.values():
                continue
            if cell in aliases:
                mapping[col_idx] = field_name
                break
    if "account_name" in mapping.values() and len(mapping) >= 2:
        return mapping
    return None


def _clean_cell(value: str | None) -> str:
    if value is None:
        return ""
    # pdfplumber can embed newlines inside a wrapped cell; flatten them.
    return re.sub(r"\s+", " ", value.replace("\n", " ")).strip()


def extract_rows(pdf_path: str) -> list[ExtractedRow]:
    """Parse the PDF and return canonicalized (but uncleaned) rows."""
    rows: list[ExtractedRow] = []
    row_index = 0

    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            for table in page.extract_tables() or []:
                col_map: dict[int, str] | None = None
                for raw_row in table:
                    if raw_row is None:
                        continue

                    # Look for the header until we find it on this table.
                    if col_map is None:
                        col_map = _match_header_row(raw_row)
                        if col_map is not None:
                            continue  # header consumed; next row is data
                        else:
                            continue  # skip pre-header noise (titles, etc.)

                    values = {f: "" for f in FIELDS}
                    raw_dump: dict[str, Any] = {}
                    for col_idx, cell in enumerate(raw_row):
                        cleaned = _clean_cell(cell)
                        raw_dump[str(col_idx)] = cleaned
                        field_name = col_map.get(col_idx)
                        if field_name:
                            values[field_name] = cleaned

                    # skip blank rows and repeated headers on later pages
                    if not any(values.values()):
                        continue
                    if _match_header_row(raw_row) is not None:
                        continue
                    if not all(values.get(f) for f in REQUIRED_FIELDS):
                        continue

                    rows.append(
                        ExtractedRow(
                            row_index=row_index,
                            page_number=page_number,
                            values=values,
                            raw=raw_dump,
                        )
                    )
                    row_index += 1

    return rows
