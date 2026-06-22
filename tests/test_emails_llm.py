"""Offline tests for the LLM draft prompt builder (no network / no API key)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from outbound_signal_engine.emails import load_config  # noqa: E402
from outbound_signal_engine.emails_llm import build_prompt, parse_subject_body  # noqa: E402

CONFIG = load_config(
    Path(__file__).resolve().parent.parent / "data" / "sample" / "email_config.sample.json"
)
STYLE = "Hey {{first_name}}, ... Best regards, Your Name"


def _prompt(segment, trigger_type=None, trigger_title=None):
    return build_prompt(
        account_name="Acme", segment=segment, industry="Retail", sub_industry="Footwear",
        trigger_type=trigger_type, trigger_title=trigger_title, config=CONFIG, style_guide=STYLE,
    )


def test_prompt_includes_style_guide_and_placeholder_rule():
    system, _ = _prompt("greenfield")
    assert STYLE in system
    assert "{{first_name}}" in system


def test_greenfield_prompt_says_build_a_program():
    _, user = _prompt("greenfield")
    assert "No affiliate or partner program" in user


def test_on_impact_prompt_flags_competitor():
    _, user = _prompt("on_impact")
    assert "Impact" in user


def test_trigger_is_passed_through():
    _, user = _prompt("greenfield", "funding", "Acme raises $20M Series B")
    assert "Acme raises $20M Series B" in user
    assert "funding" in user


def test_no_trigger_falls_back_to_industry_observation():
    _, user = _prompt("greenfield")
    assert "none found" in user


def test_social_proof_brands_in_prompt():
    _, user = _prompt("greenfield")  # footwear vertical in sample config
    assert "Acme Footwear" in user


def test_parse_subject_body_plain_json():
    d = parse_subject_body('{"subject": "Hi", "body": "Line1\\nLine2"}')
    assert d == {"subject": "Hi", "body": "Line1\nLine2"}


def test_parse_subject_body_with_code_fence_and_prose():
    raw = 'Here you go:\n```json\n{"subject": "S", "body": "B"}\n```'
    d = parse_subject_body(raw)
    assert d["subject"] == "S" and d["body"] == "B"


def test_parse_subject_body_fallback_to_body():
    d = parse_subject_body("just some text, no json")
    assert d["subject"] == "" and "just some text" in d["body"]
