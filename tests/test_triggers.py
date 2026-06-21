"""Offline tests for trigger classification + scoring.

Run with:  python -m pytest tests/test_triggers.py -q
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from outbound_signal_engine.news import Article, dedupe  # noqa: E402
from outbound_signal_engine.triggers import (  # noqa: E402
    TRIGGER_SCORE_MAX,
    classify,
    recency_factor,
    score_account,
)

NOW = datetime(2026, 6, 21, tzinfo=timezone.utc)


def _art(title, days_ago=5, url=None):
    return Article(title=title, url=url,
                   published_at=NOW - timedelta(days=days_ago), source="t")


def test_classify_types():
    assert classify("Acme raises $20M Series B") == "funding"
    assert classify("BigCo acquires Acme") == "acquisition"
    assert classify("Acme appoints new CEO") == "leadership"
    assert classify("Acme launches new collection") == "product_launch"
    assert classify("Acme expands into Europe") == "expansion"
    assert classify("Acme partners with Nike") == "partnership"


def test_classify_non_trigger_is_none():
    assert classify("Do you sleep with the TV on?") is None
    assert classify("The best meat delivery services of 2026") is None


def test_recency_decays():
    assert recency_factor(NOW, NOW) == 1.0
    assert recency_factor(NOW - timedelta(days=20), NOW) == 0.8
    assert recency_factor(NOW - timedelta(days=200), NOW) == 0.0
    assert recency_factor(None, NOW) == 0.3


def test_funding_recent_scores_high():
    total, scored = score_account([_art("Acme raises $30M Series B", 3)], NOW)
    assert scored[0].trigger_type == "funding"
    assert total == 30  # weight 3 * 1.0 * BASE 10


def test_score_capped_and_sorted():
    arts = [
        _art("Acme raises $50M Series C", 2),       # funding 30
        _art("Acme acquires Rival Inc", 2),          # acquisition 30
        _art("Acme launches app", 2),                # launch 20
    ]
    total, scored = score_account(arts, NOW)
    assert total == TRIGGER_SCORE_MAX            # 80 capped to 40
    assert scored[0].score >= scored[-1].score   # strongest first


def test_old_news_ignored():
    total, scored = score_account([_art("Acme raises $10M", days_ago=300)], NOW)
    assert total == 0 and scored == []


def test_dedupe_by_url_and_title():
    arts = [
        Article("Same", "https://x.com/a?utm=1", NOW, "broad"),
        Article("Same", "https://x.com/a?utm=2", NOW, "targeted"),  # same path
    ]
    assert len(dedupe(arts)) == 1
