"""First-touch email DRAFT generation (Milestone 5).

Turns an account's segment + trigger + vertical into a ready-to-edit first-touch
draft, using the rep's own templates (loaded from config — never hard-coded, so
proprietary messaging stays out of the repo).

DRAFTS ONLY. Nothing here sends email. Output is meant for human review/edit.

Mapping:
  * segment greenfield        -> "off_program" template
  * segment with a program    -> "on_program" template
  * top trigger               -> the "I noticed ..." observation hook
  * account industry/sub      -> social-proof brands + partner types for the vertical
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Map an account's (industry, sub_industry) text to a social-proof vertical key.
# First keyword found wins. Keys must exist in the config's social_proof map
# (falls back to "default").
_VERTICAL_KEYWORDS: list[tuple[str, str]] = [
    ("activewear", "activewear"), ("athleisure", "activewear"),
    ("menswear", "fashion_mens"), ("womenswear", "fashion_womens"),
    ("apparel", "fashion_womens"), ("clothing", "fashion_womens"), ("fashion", "fashion_womens"),
    ("haircare", "haircare"), ("hair", "haircare"),
    ("beauty", "beauty"), ("cosmetic", "beauty"), ("wellness", "beauty"),
    ("jewel", "jewelry"),
    ("watch", "watches"),
    ("shoe", "footwear"), ("footwear", "footwear"),
    ("beverage", "beverages"), ("drink", "beverages"),
    ("supplement", "supplements"), ("nutrition", "supplements"), ("health", "supplements"),
    ("food", "dtc_food"), ("fmcg", "dtc_food"), ("grocery", "dtc_food"),
    ("furniture", "homegoods"), ("home & garden", "home_garden"), ("garden", "home_garden"),
    ("home", "homegoods"),
    ("pet", "pet"),
    ("child", "kids"), ("kids", "kids"), ("baby", "kids"),
    ("electronic", "electronics"),
    ("financial", "saas"), ("software", "saas"), ("saas", "saas"), ("fintech", "saas"),
    ("subscription", "subscription"), ("books", "subscription"),
    ("music", "ecommerce"), ("retail", "ecommerce"),
]

# Per trigger type, how to phrase the "I noticed ..." observation. {company} and
# {detail} (a cleaned headline fragment) are filled in.
_OBSERVATION_BY_TYPE: dict[str, str] = {
    "funding": "I noticed {company} recently raised new funding — usually a strong moment to invest in scalable acquisition channels.",
    "acquisition": "I noticed {company} has been in the news around an acquisition — moments like that often reshape how growth channels are prioritized.",
    "leadership": "I noticed {company} recently brought on new leadership — often a great time to revisit how the partner channel is set up.",
    "product_launch": "I noticed {company} has been launching new products lately — usually the kind of momentum a partner program can amplify.",
    "expansion": "I noticed {company} is expanding — usually when companies hit that stage, the partner channel becomes a bigger lever for discovery.",
    "partnership": "I noticed {company} has been building new partnerships recently — a natural fit for a more scalable partner program.",
    "growth_award": "I noticed {company} has been getting recognition for its growth lately — exciting momentum to build a partner channel on.",
    "earnings": "I noticed {company} has had a notable stretch of business momentum recently.",
}
_OBSERVATION_FALLBACK = (
    "I've been following {company} and the work you're doing in the {industry} space."
)


@dataclass
class Draft:
    account_id: str | None
    account_name: str
    segment: str
    template: str          # 'off_program' | 'on_program'
    subject: str
    body: str
    used_trigger: bool


def load_config(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def vertical_for(industry: str | None, sub_industry: str | None) -> str:
    haystack = f"{industry or ''} {sub_industry or ''}".lower()
    for kw, vert in _VERTICAL_KEYWORDS:
        if kw in haystack:
            return vert
    return "default"


def _pick(config_map: dict, vertical: str, fallback_key: str = "default"):
    return config_map.get(vertical) or config_map.get(fallback_key)


def _observation(trigger_type: str | None, company: str, industry: str | None) -> tuple[str, bool]:
    if trigger_type and trigger_type in _OBSERVATION_BY_TYPE:
        return _OBSERVATION_BY_TYPE[trigger_type].format(company=company), True
    ind = (industry or "your").strip() or "your"
    return _OBSERVATION_FALLBACK.format(company=company, industry=ind), False


def first_name(contact_name: str | None) -> str:
    # No contact data yet (contact enrichment is a future milestone), so leave a
    # fill-in placeholder rather than a generic "there".
    if not contact_name:
        return "{{first_name}}"
    return contact_name.strip().split()[0]


def _subject(segment: str, company: str, trigger_type: str | None) -> str:
    if trigger_type == "funding":
        return f"Partnerships for {company} after the raise"
    if trigger_type == "expansion":
        return f"Scaling {company}'s partner channel"
    if segment == "greenfield":
        return f"A partner channel for {company}?"
    return f"Quick question on {company}'s affiliate program"


def generate_draft(
    *,
    account_id: str | None,
    account_name: str,
    segment: str,
    industry: str | None,
    sub_industry: str | None,
    trigger_type: str | None,
    config: dict[str, Any],
    contact_name: str | None = None,
) -> Draft:
    """Render a first-touch draft for one account. Pure string assembly."""
    template_key = "off_program" if segment == "greenfield" else "on_program"
    template = config["templates"][template_key]
    vertical = vertical_for(industry, sub_industry)

    brands = _pick(config["social_proof"], vertical) or ["our clients"]
    social_proof = ", ".join(brands[:-1]) + (f", and {brands[-1]}" if len(brands) > 1 else brands[0])
    partner_types = _pick(config["partner_types"], vertical) or "creator, publisher, and affiliate"

    observation, used = _observation(trigger_type, account_name, industry)

    body = template.format(
        first_name=first_name(contact_name),
        company=account_name,
        observation=observation,
        platform=config.get("platform", "our platform"),
        social_proof=social_proof,
        partner_types=partner_types,
        cta=config.get("cta", "Would you be open to a quick chat?"),
        sender=config.get("sender", ""),
        booking=config.get("booking", ""),
    )
    body = re.sub(r"\n{3,}", "\n\n", body).strip()

    return Draft(
        account_id=account_id,
        account_name=account_name,
        segment=segment,
        template=template_key,
        subject=_subject(segment, account_name, trigger_type),
        body=body,
        used_trigger=used,
    )
