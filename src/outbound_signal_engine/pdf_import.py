"""Extract account rows from a Salesforce Printable-View PDF.

Salesforce "Printable View" PDFs draw the list as a table with **horizontal row
rules but no vertical column rules**. That breaks naive table extraction: every
row's five columns collapse into a single cell. So instead of trusting cell
segmentation, we reconstruct columns from the geometry:

  1. find the table's horizontal row bands (pdfplumber detects these reliably);
  2. locate the header row and read each column's x-position ("anchor");
  3. for every data row, assign each word to the nearest column anchor by x0,
     then join the words per column.

This is robust to wrapped/multi-line cells (continuation words sit in the same
x-band) and to PDFs that *do* have vertical rules (words still carry x0).

If a real export doesn't parse, the usual fix is a header alias in config.py —
not a change here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import pdfplumber

from .config import FIELDS, HEADER_ALIASES, REQUIRED_FIELDS

def _norm(text: str | None) -> str:
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# Normalized header text -> field. We register both the full normalized alias
# ("sub industry") and its first token ("sub") so a header word can be matched
# whether it arrives whole ("Sub-Industry") or split across words
# ("Account" "Name"). Everything is normalized the same way as the PDF words,
# so hyphens/spaces never cause a mismatch.
_HEADER_LOOKUP: dict[str, str] = {}
for _field, _aliases in HEADER_ALIASES.items():
    for _alias in _aliases:
        _na = _norm(_alias)
        if not _na:
            continue
        _HEADER_LOOKUP.setdefault(_na, _field)
        _HEADER_LOOKUP.setdefault(_na.split()[0], _field)


@dataclass
class ExtractedRow:
    """One row pulled from the PDF, before cleaning/dedup."""

    row_index: int
    page_number: int
    values: dict[str, str]  # canonical_field -> raw cell text
    raw: dict[str, Any] = field(default_factory=dict)


def _vcenter(word: dict) -> float:
    return (word["top"] + word["bottom"]) / 2


def _find_anchors(pages) -> dict[str, float] | None:
    """Locate column anchors {field: x0} from the header row, scanning pages.

    Groups words into lines by their vertical position, then picks the line that
    matches the most distinct header fields. Returns the x0 of each field's
    header word.
    """
    for page in pages:
        words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
        # cluster words into lines by rounded vertical position
        lines: dict[int, list[dict]] = {}
        for w in words:
            lines.setdefault(round(w["top"]), []).append(w)

        best: dict[str, float] | None = None
        best_count = 0
        for _, line_words in lines.items():
            anchors: dict[str, float] = {}
            for w in sorted(line_words, key=lambda x: x["x0"]):
                fld = _HEADER_LOOKUP.get(_norm(w["text"]))
                if fld and fld not in anchors:
                    anchors[fld] = w["x0"]
            # need account_name plus at least one more to trust it's the header
            if "account_name" in anchors and len(anchors) > best_count:
                best, best_count = anchors, len(anchors)
        if best and best_count >= 2:
            return best
    return None


# How far left of its header a column's text may start (font metrics make URLs
# begin ~1pt left of the header word). Must stay well under the smallest gap
# between adjacent column anchors.
_LEFT_EDGE_TOL = 8.0


def _assign_field(x0: float, sorted_anchors: list[tuple[str, float]]) -> str:
    """Assign a word to the rightmost column whose left edge it has reached.

    Columns are treated as left-aligned bands (anchor = left edge), not centers.
    A wide column like Account Name fills its full width, so a long name's
    trailing word stays in the name column instead of bleeding into Website —
    which a nearest-center rule gets wrong.
    """
    chosen = sorted_anchors[0][0]
    for field_name, ax in sorted_anchors:
        if x0 >= ax - _LEFT_EDGE_TOL:
            chosen = field_name
        else:
            break
    return chosen


def _clean_cell(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\n", " ")).strip()


def _is_header_line(values: dict[str, str]) -> bool:
    return _HEADER_LOOKUP.get(_norm(values.get("account_name"))) == "account_name"


def extract_rows(pdf_path: str) -> list[ExtractedRow]:
    """Parse the PDF and return canonicalized (but uncleaned) rows."""
    rows: list[ExtractedRow] = []
    row_index = 0

    with pdfplumber.open(pdf_path) as pdf:
        anchors = _find_anchors(pdf.pages)
        if not anchors:
            return rows  # caller surfaces the "no header recognized" message
        sorted_anchors = sorted(anchors.items(), key=lambda kv: kv[1])

        for page_number, page in enumerate(pdf.pages, start=1):
            tables = page.find_tables()
            if not tables:
                continue
            table = max(tables, key=lambda t: len(t.rows))
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)

            for trow in table.rows:
                x0, top, x1, bottom = trow.bbox
                band = [
                    w for w in words
                    if top <= _vcenter(w) <= bottom and x0 - 2 <= w["x0"] <= x1 + 2
                ]
                if not band:
                    continue

                buckets: dict[str, list[dict]] = {f: [] for f in FIELDS}
                for w in band:
                    buckets[_assign_field(w["x0"], sorted_anchors)].append(w)

                values = {}
                for fld, ws in buckets.items():
                    ws.sort(key=lambda x: (round(x["top"]), x["x0"]))
                    values[fld] = _clean_cell(" ".join(w["text"] for w in ws))

                if not any(values.values()):
                    continue
                if _is_header_line(values):
                    continue
                if not all(values.get(f) for f in REQUIRED_FIELDS):
                    continue

                rows.append(
                    ExtractedRow(
                        row_index=row_index,
                        page_number=page_number,
                        values=values,
                        raw={"bbox": [round(c, 1) for c in trow.bbox], **values},
                    )
                )
                row_index += 1

    return rows
