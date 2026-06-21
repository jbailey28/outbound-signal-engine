"""Tests for M4 opportunity scoring.

Run with:  python -m pytest tests/test_scoring.py -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from outbound_signal_engine.scoring import (  # noqa: E402
    SEGMENT_SCORES,
    classify_segment,
    score_account,
)


def _score(has_program, platform, trigger=0):
    return score_account(
        account_id=None, account_name="Acme",
        has_program=has_program, platform=platform, trigger_score=trigger,
    )


def test_greenfield_is_highest():
    s = _score(False, "unknown")
    assert s.segment == "greenfield"
    assert s.fit_score == SEGMENT_SCORES["greenfield"]


def test_non_impact_platform_is_high():
    assert _score(True, "rakuten").segment == "non_impact_platform"
    assert _score(True, "in_house").segment == "non_impact_platform"
    assert _score(True, "avantlink").fit_score == 70


def test_on_impact_is_lowest():
    s = _score(True, "impact")
    assert s.segment == "on_impact"
    assert s.fit_score == 20


def test_unknown_flagged_for_review():
    s = _score(None, None)
    assert s.segment == "unknown"
    assert s.needs_review is True


def test_ordering_matches_priority():
    greenfield = _score(False, None).total_score
    other = _score(True, "cj").total_score
    on_impact = _score(True, "impact").total_score
    assert greenfield > other > on_impact


def test_trigger_score_adds_on_top():
    s = _score(False, None, trigger=25)
    assert s.total_score == s.fit_score + 25


def test_classify_segment_direct():
    assert classify_segment(False, None) == "greenfield"
    assert classify_segment(True, "IMPACT") == "on_impact"  # case-insensitive
    assert classify_segment(True, "awin") == "non_impact_platform"
    assert classify_segment(None, None) == "unknown"
