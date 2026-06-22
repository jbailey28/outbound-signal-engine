"""Tests for first-touch draft generation (uses the committed sample config).

Run with:  python -m pytest tests/test_emails.py -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from outbound_signal_engine.emails import (  # noqa: E402
    first_name,
    generate_draft,
    load_config,
    vertical_for,
)

CONFIG = load_config(
    Path(__file__).resolve().parent.parent / "data" / "sample" / "email_config.sample.json"
)


def _draft(segment, trigger=None, industry="Retail", sub="Footwear"):
    return generate_draft(
        account_id="x", account_name="Acme", segment=segment,
        industry=industry, sub_industry=sub, trigger_type=trigger, config=CONFIG,
    )


def test_greenfield_uses_off_program_template():
    d = _draft("greenfield")
    assert d.template == "off_program"
    assert "didn't see an affiliate or partner program" in d.body


def test_has_program_uses_on_program_template():
    d = _draft("non_impact_platform")
    assert d.template == "on_program"
    assert "already an affiliate program" in d.body


def test_trigger_drives_observation():
    d = _draft("greenfield", trigger="funding")
    assert d.used_trigger is True
    assert "raised new funding" in d.body


def test_no_trigger_uses_fallback_observation():
    d = _draft("greenfield", trigger=None)
    assert d.used_trigger is False
    assert "following Acme" in d.body


def test_vertical_mapping():
    assert vertical_for("Retail & Shopping", "Health & Beauty") == "beauty"
    assert vertical_for("Retail", "Jewellery") == "jewelry"
    assert vertical_for("Retail", "Menswear") == "fashion_mens"
    # "menswear" is a substring of "womenswear" — must not false-match
    assert vertical_for("Retail", "Jewellery; Womenswear") == "fashion_womens"
    assert vertical_for("Mystery", "Mystery") == "default"


def test_social_proof_filled_from_config():
    d = _draft("greenfield", industry="Retail", sub="Footwear")
    # sample config footwear brands
    assert "Acme Footwear" in d.body
    assert "{social_proof}" not in d.body  # no leftover placeholders


def test_no_unfilled_placeholders():
    d = _draft("non_impact_platform", trigger="expansion")
    assert "{" not in d.body.replace("{{first_name}}", "")  # only the name stays templated


def test_first_name_placeholder():
    assert first_name(None) == "{{first_name}}"
    assert first_name("Naomi Smith") == "Naomi"
