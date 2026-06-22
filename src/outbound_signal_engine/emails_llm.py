"""LLM-powered first-touch draft generation (Milestone 5, opt-in).

Upgrades the template-fill drafts to natural, varied prose written by Claude,
using the rep's own emails as a few-shot style guide. Opt-in: the default
generator stays template-fill (free, no key); this path runs only when the user
passes --llm and sets ANTHROPIC_API_KEY.

Still DRAFTS ONLY — nothing here sends email. The model is instructed to leave a
{{first_name}} placeholder and never invent facts about the company beyond the
trigger we hand it.

Model: defaults to claude-opus-4-8; override with the ANTHROPIC_MODEL env var
(e.g. claude-haiku-4-5 or claude-sonnet-4-6 for lower cost).
"""

from __future__ import annotations

import json
import os
from typing import Any

from .emails import Draft, _pick, vertical_for

DEFAULT_MODEL = "claude-opus-4-8"

# Constrains the response so we always get a clean subject + body.
_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {"type": "string"},
        "body": {"type": "string"},
    },
    "required": ["subject", "body"],
    "additionalProperties": False,
}


def _program_status(segment: str) -> str:
    if segment == "greenfield":
        return "No affiliate or partner program found (greenfield — biggest opportunity)."
    if segment == "on_impact":
        return "Already running a program on Impact (our competitor)."
    return "Already has an affiliate/partner program (on a non-Impact platform or in-house)."


def build_prompt(
    *,
    account_name: str,
    segment: str,
    industry: str | None,
    sub_industry: str | None,
    trigger_type: str | None,
    trigger_title: str | None,
    config: dict[str, Any],
    style_guide: str,
) -> tuple[str, str]:
    """Assemble (system, user) prompts. Pure — unit-testable without the network."""
    vertical = vertical_for(industry, sub_industry)
    brands = _pick(config["social_proof"], vertical) or ["our clients"]
    partner_types = _pick(config["partner_types"], vertical) or "creator, publisher, and affiliate"

    system = (
        f"You are {config.get('sender', 'a rep')}, an Account Executive at "
        f"{config.get('platform', 'our company')} (an affiliate/partner-marketing platform). "
        "You write concise, genuine first-touch prospecting emails. Match the voice, "
        "structure, and length of the EXAMPLES below exactly — same warmth, same brevity, "
        "no corporate filler.\n\n"
        "RULES:\n"
        "- This is a DRAFT for the rep to review; never claim it will be sent.\n"
        "- Address the recipient as the literal placeholder {{first_name}} (we don't have the contact's name).\n"
        "- Open with ONE specific observation about the company. If a recent trigger is "
        "provided, build the observation on it; otherwise use a light, honest industry observation. "
        "Do NOT invent funding, hires, launches, or any fact beyond the trigger given.\n"
        f"- If the company has no program, pitch building one; if it already has one, ask whether "
        "it's delivering — never name their current platform.\n"
        "- Name the three provided social-proof brands as companies that use the platform.\n"
        "- End with a short call-to-action question and the sign-off, then a line '[ Book a Meeting ]'.\n"
        "- Keep it under ~150 words. No subject-line clickbait.\n\n"
        f"EXAMPLES (the rep's real emails — match this voice):\n{style_guide}"
    )

    user = (
        f"Write a first-touch email draft.\n"
        f"Company: {account_name}\n"
        f"Program status: {_program_status(segment)}\n"
        f"Industry: {industry or 'unknown'} / {sub_industry or 'unknown'}\n"
        f"Social-proof brands to cite (same vertical): {', '.join(brands[:3])}\n"
        f"Relevant partner types for the observation: {partner_types}\n"
    )
    if trigger_type and trigger_title:
        user += f"Recent trigger ({trigger_type}): \"{trigger_title}\"\n"
    else:
        user += "Recent trigger: none found — use a light industry observation.\n"
    user += "\nReturn a subject and the email body."
    return system, user


def generate_draft_llm(
    *,
    account_id: str | None,
    account_name: str,
    segment: str,
    industry: str | None,
    sub_industry: str | None,
    trigger_type: str | None,
    trigger_title: str | None,
    config: dict[str, Any],
    style_guide: str,
    client=None,
    model: str | None = None,
) -> Draft:
    """Generate a draft via Claude. Raises on API error (caller can fall back)."""
    from anthropic import Anthropic  # lazy: template-only users don't need the SDK

    client = client or Anthropic()
    model = model or os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)
    system, user = build_prompt(
        account_name=account_name, segment=segment, industry=industry,
        sub_industry=sub_industry, trigger_type=trigger_type, trigger_title=trigger_title,
        config=config, style_guide=style_guide,
    )

    resp = client.messages.create(
        model=model,
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"format": {"type": "json_schema", "schema": _OUTPUT_SCHEMA}},
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("model refused to draft this email")
    text = next(b.text for b in resp.content if b.type == "text")
    data = json.loads(text)

    return Draft(
        account_id=account_id,
        account_name=account_name,
        segment=segment,
        template="llm",
        subject=data["subject"].strip(),
        body=data["body"].strip(),
        used_trigger=bool(trigger_type and trigger_title),
    )
