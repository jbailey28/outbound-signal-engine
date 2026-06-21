"""Tests for the Tier-1 affiliate-signal classifier and fingerprint integrity.

Run with:  python -m pytest tests/test_signals.py -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from outbound_signal_engine.signals import (  # noqa: E402
    PLATFORMS,
    classify_from_competitor,
)


def _classify(value):
    return classify_from_competitor(
        value, account_id=None, account_name="Acme", domain="acme.com"
    )


def test_known_platform_high_confidence():
    s = _classify("Impact")
    assert s.platform == "impact"
    assert s.has_program is True
    assert s.confidence == "high"
    assert s.needs_scrape is False


def test_platform_aliases_resolve():
    assert _classify("Commission Junction").platform == "cj"
    assert _classify("Affiliate Window").platform == "awin"
    assert _classify("LinkShare").platform == "rakuten"


def test_substring_match():
    s = _classify("currently running on Rakuten")
    assert s.platform == "rakuten"
    assert s.has_program is True


def test_no_competitor_is_unknown_and_needs_scrape():
    s = _classify("No Competitor")
    assert s.platform == "unknown"
    assert s.has_program is None
    assert s.needs_scrape is True


def test_blank_needs_scrape():
    s = _classify("")
    assert s.has_program is None
    assert s.needs_scrape is True
    assert _classify(None).needs_scrape is True


def test_unrecognized_value_flagged_for_scrape():
    s = _classify("SomeUnknownNetwork XYZ")
    assert s.platform == "unknown"
    assert s.needs_scrape is True
    assert s.evidence.get("raw_value") == "SomeUnknownNetwork XYZ"


def test_fingerprints_are_unique_and_well_formed():
    keys = [p.key for p in PLATFORMS]
    assert len(keys) == len(set(keys)), "platform keys must be unique"
    # network domains must not collide across platforms (would break Tier 2)
    seen = {}
    for p in PLATFORMS:
        assert p.network_domains, f"{p.key} has no network domains"
        for d in p.network_domains:
            assert d not in seen, f"domain {d} shared by {seen.get(d)} and {p.key}"
            seen[d] = p.key
