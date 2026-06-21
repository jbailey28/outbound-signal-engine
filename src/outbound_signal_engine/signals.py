"""Affiliate / partner-program signal knowledge base + Tier-1 classifier.

This module is the heart of Milestone 2. It holds:

  * PLATFORMS  — fingerprints for the major affiliate networks: the names they
                 show up as in a CRM ("Competitors" column) AND the tracking
                 domains that leak into a brand's website HTML (used by Tier 2).
  * PROGRAM_PATHS — common URL paths where brands host an affiliate/partner
                 program (probed in Tier 2).
  * classify_from_competitor() — Tier 1: derive a platform signal from the
                 existing Competitors value, no network calls.

Keeping all the detection knowledge in one auditable place means adding a new
network is a data edit here, not a code change elsewhere.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Platform:
    key: str                      # normalized id stored in the DB
    display: str                  # human label
    aliases: list[str]            # how it appears in a "Competitors" column
    network_domains: list[str]    # tracking domains seen in brand HTML (Tier 2)


# Fingerprints for the major affiliate / partner networks. network_domains are
# the redirect/tracking hosts that show up in a brand's outbound affiliate links
# — finding one on a site is strong evidence they run a program on that network.
PLATFORMS: list[Platform] = [
    Platform(
        "impact", "impact.com",
        ["impact", "impact.com", "impact radius", "impactradius"],
        ["impact.com", "pxf.io", "ojrq.net", "sjv.io", "7eer.net", "evyy.net", "ircdn.net"],
    ),
    Platform(
        "rakuten", "Rakuten Advertising",
        ["rakuten", "rakuten advertising", "linkshare", "rakuten linkshare"],
        ["linksynergy.com", "rakutenadvertising.com"],
    ),
    Platform(
        "cj", "CJ Affiliate",
        ["cj", "cj affiliate", "commission junction", "conversant"],
        ["cj.com", "anrdoezrs.net", "dpbolvw.net", "jdoqocy.com", "tkqlhce.com",
         "kqzyfj.com", "ftjcfx.com", "qksrv.net", "emjcd.com"],
    ),
    Platform(
        "awin", "Awin",
        ["awin", "affiliate window", "zanox"],
        ["awin1.com", "dwin1.com", "zenaps.com"],
    ),
    Platform(
        "shareasale", "ShareASale",
        ["shareasale", "share a sale"],
        ["shareasale.com", "shrsl.com"],
    ),
    Platform(
        "partnerstack", "PartnerStack",
        ["partnerstack", "partner stack"],
        ["partnerstack.com", "grsm.io"],
    ),
    Platform(
        "pepperjam", "Pepperjam / Ascend",
        ["pepperjam", "ascend", "ebay enterprise"],
        ["pepperjamnetwork.com", "gopjn.com", "pntra.com", "pntrac.com", "pntrs.com"],
    ),
    Platform(
        "partnerize", "Partnerize",
        ["partnerize", "performance horizon"],
        ["prf.hn", "performancehorizon.com"],
    ),
    Platform(
        "refersion", "Refersion",
        ["refersion"],
        ["refersion.com"],
    ),
    Platform(
        "tune", "TUNE",
        ["tune", "hasoffers", "has offers"],
        ["hasoffers.com", "go2cloud.org"],
    ),
    Platform(
        "skimlinks", "Skimlinks",
        ["skimlinks"],
        ["skimlinks.com", "skimresources.com"],
    ),
    Platform(
        "avantlink", "AvantLink",
        ["avantlink"],
        ["avantlink.com", "avmws.com"],
    ),
]

# Values in a Competitors column that explicitly mean "no competing platform
# found" — informative but NOT proof of no program, so Tier 2 should still run.
_NO_COMPETITOR_VALUES = {"no competitor", "no competitors", "none", "n/a", "na"}

# Common paths a brand uses to host an affiliate / partner / ambassador program.
# Probed in Tier 2 (order = rough likelihood).
PROGRAM_PATHS: list[str] = [
    "/affiliates", "/affiliate", "/affiliate-program", "/affiliate-programme",
    "/partners", "/partner", "/partner-program", "/partnerships",
    "/ambassador", "/ambassadors", "/ambassador-program",
    "/creators", "/creator-program", "/influencers", "/influencer-program",
    "/refer", "/referral", "/referrals", "/refer-a-friend",
    "/pages/affiliates", "/pages/affiliate-program", "/pages/ambassadors",
]


@dataclass
class Signal:
    """A derived affiliate/partner-program signal for one account."""

    account_id: str | None
    account_name: str
    domain: str | None
    has_program: bool | None          # True / False / None(unknown)
    platform: str                     # platform key or 'unknown'/'in_house'
    source: str                       # 'competitors_column' | 'website_scrape'
    confidence: str                   # 'low' | 'medium' | 'high'
    evidence: dict[str, Any] = field(default_factory=dict)
    needs_scrape: bool = False        # Tier-1 couldn't resolve -> Tier-2 candidate


def _norm(value: str | None) -> str:
    if not value:
        return ""
    value = value.lower()
    value = re.sub(r"[^a-z0-9 ]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


# alias -> platform key, precomputed for fast lookup
_ALIAS_TO_KEY: dict[str, str] = {}
for _p in PLATFORMS:
    for _a in _p.aliases:
        _ALIAS_TO_KEY[_norm(_a)] = _p.key


def platform_by_key(key: str) -> Platform | None:
    return next((p for p in PLATFORMS if p.key == key), None)


def classify_from_competitor(
    competitor_value: str | None,
    *,
    account_id: str | None,
    account_name: str,
    domain: str | None,
) -> Signal:
    """Tier 1: map a Competitors-column value to a platform signal (no fetch).

    - A recognized network name -> high-confidence "runs a program on <platform>".
    - "No Competitor"/blank -> unknown; flagged for Tier-2 website scraping.
    """
    norm = _norm(competitor_value)

    if not norm:
        return Signal(account_id, account_name, domain, None, "unknown",
                      "competitors_column", "low",
                      {"reason": "blank competitors value"}, needs_scrape=True)

    if norm in _NO_COMPETITOR_VALUES:
        return Signal(account_id, account_name, domain, None, "unknown",
                      "competitors_column", "low",
                      {"reason": "explicit 'no competitor' — not proof of no program"},
                      needs_scrape=True)

    # exact alias match, then substring (handles "running on Impact", etc.)
    key = _ALIAS_TO_KEY.get(norm)
    if key is None:
        for alias, k in _ALIAS_TO_KEY.items():
            if re.search(rf"\b{re.escape(alias)}\b", norm):
                key = k
                break

    if key:
        return Signal(account_id, account_name, domain, True, key,
                      "competitors_column", "high",
                      {"matched_alias": norm, "raw_value": competitor_value})

    # a non-empty but unrecognized value — record it, still worth scraping
    return Signal(account_id, account_name, domain, None, "unknown",
                  "competitors_column", "low",
                  {"reason": "unrecognized competitors value", "raw_value": competitor_value},
                  needs_scrape=True)
