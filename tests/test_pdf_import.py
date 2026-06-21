"""End-to-end parse test against the synthetic sample PDF.

Guards the geometry-based column reconstruction (header anchors, left-edge
assignment, multi-line cells) and the clean/dedupe step. Regenerates the sample
PDF if it's missing so the test is self-contained.

Run with:  python -m pytest tests/test_pdf_import.py -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from outbound_signal_engine.accounts import build_clean_accounts  # noqa: E402
from outbound_signal_engine.pdf_import import extract_rows  # noqa: E402

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "sample" / "sample_accounts.pdf"


def _ensure_sample():
    if not SAMPLE.exists():
        import make_sample_pdf  # noqa: F401  (script in tests/)

        make_sample_pdf.build()


def test_sample_extracts_seven_rows():
    _ensure_sample()
    rows = extract_rows(str(SAMPLE))
    assert len(rows) == 7  # 7 data rows, header excluded


def test_dedup_collapses_acme_duplicate():
    _ensure_sample()
    accounts = build_clean_accounts(extract_rows(str(SAMPLE)))
    assert len(accounts) == 6  # the two Acme rows collapse on domain
    domains = [a.domain for a in accounts if a.domain]
    assert domains.count("acmeretail.com") == 1


def test_industry_and_subindustry_are_separate_columns():
    _ensure_sample()
    accounts = {a.account_name: a for a in build_clean_accounts(extract_rows(str(SAMPLE)))}
    globex = accounts["Globex Corporation"]
    assert globex.industry == "Technology"
    assert globex.sub_industry == "SaaS"
    assert globex.domain == "globex.co.uk"  # multi-part TLD preserved


def test_row_without_website_falls_back_to_name_key():
    _ensure_sample()
    accounts = {a.account_name: a for a in build_clean_accounts(extract_rows(str(SAMPLE)))}
    wayne = accounts["Wayne Enterprises"]
    assert wayne.domain is None
    assert wayne.dedup_key.startswith("name:")
    assert wayne.competitors == "Rakuten"
