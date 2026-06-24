"""Tests for the contacted-accounts ledger (rotation across runs)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from outbound_signal_engine.contacted import (  # noqa: E402
    load_contacted_ids,
    mark_contacted,
    reset_contacted,
)


def test_mark_then_load(tmp_path):
    p = tmp_path / "contacted.csv"
    added = mark_contacted([{"account_id": "a1", "account_name": "Acme"},
                            {"account_id": "a2", "account_name": "Globex"}], path=p)
    assert added == 2
    assert load_contacted_ids(p) == {"a1", "a2"}


def test_dedup_on_repeat(tmp_path):
    p = tmp_path / "contacted.csv"
    mark_contacted([{"account_id": "a1", "account_name": "Acme"}], path=p)
    added = mark_contacted([{"account_id": "a1", "account_name": "Acme"},
                            {"account_id": "a3", "account_name": "Initech"}], path=p)
    assert added == 1  # a1 already there
    assert load_contacted_ids(p) == {"a1", "a3"}


def test_reset(tmp_path):
    p = tmp_path / "contacted.csv"
    mark_contacted([{"account_id": "a1", "account_name": "Acme"}], path=p)
    assert reset_contacted(p) is True
    assert load_contacted_ids(p) == set()
    assert reset_contacted(p) is False  # nothing to remove now


def test_load_missing_file_is_empty(tmp_path):
    assert load_contacted_ids(tmp_path / "nope.csv") == set()
