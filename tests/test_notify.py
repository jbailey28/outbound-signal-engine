"""Offline tests for Discord message formatting."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from outbound_signal_engine.notify import format_draft  # noqa: E402

ROW = {
    "account_name": "FOX'S", "segment": "greenfield", "score": 140,
    "trigger_type": "acquisition", "website": "https://foxs.com",
    "instagram": "https://www.instagram.com/foxsdesigner_",
    "subject": "Partnerships for FOX'S", "body": "Hey {{first_name}},\n\n...",
}


def test_format_includes_key_fields():
    msg = format_draft(1, ROW)
    assert "1. FOX'S" in msg
    assert "greenfield" in msg and "score 140" in msg
    assert "https://foxs.com" in msg
    assert "instagram.com/foxsdesigner_" in msg
    assert "Partnerships for FOX'S" in msg
    assert "{{first_name}}" in msg


def test_format_handles_missing_optional_fields():
    msg = format_draft(2, {**ROW, "website": "", "instagram": "", "trigger_type": ""})
    assert "trigger: none" in msg
    assert "—" in msg  # placeholder for missing website/instagram
