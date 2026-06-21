"""Tier-2: detect affiliate/partner programs by reading a brand's website.

Two kinds of evidence, strongest first:

  1. Network fingerprint — a known affiliate-network tracking domain (e.g.
     Impact's `pxf.io`, CJ's `anrdoezrs.net`) appears in the page HTML. This both
     proves a program exists AND identifies the platform. High confidence.

  2. Program page — a link or path like `/affiliates`, `/ambassador`,
     `/partner-program`. Proves a program exists; platform is in-house/unknown
     unless a fingerprint also turns up on that page. Medium confidence.

We read the homepage, follow up to a couple of program links, and (only if the
homepage gave us nothing) probe a short list of common program paths. Every
fetch is recorded for audit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .signals import PLATFORMS, PROGRAM_PATHS, Signal
from .web import FetchResult, fetch, make_session

# Hrefs whose path looks like a program page.
_PROGRAM_HREF = re.compile(
    r"/(affiliates?|partners?|partner-program|partnerships?|ambassadors?|"
    r"ambassador-program|creators?|creator-program|influencers?|"
    r"influencer-program|refer|referrals?|refer-a-friend)(/|$|\?|-)",
    re.I,
)
# Anchor text that names a program explicitly (lower false positives than href).
_PROGRAM_TEXT = re.compile(
    r"\b(affiliate|ambassador|referral program|creator program|"
    r"partner program|influencer program)\b",
    re.I,
)
# Words that confirm a probed path is really a program page.
_PROGRAM_CONFIRM = re.compile(
    r"\b(affiliate|ambassador|commission|referral|partner program|"
    r"earn|payout|join (our|the) program)\b",
    re.I,
)

# How many common paths to probe when the homepage yields nothing.
_PROBE_BUDGET = 5


@dataclass
class ScrapeOutcome:
    signal: Signal
    fetches: list[dict] = field(default_factory=list)  # audit rows


def scan_networks(html: str) -> list[tuple[str, str]]:
    """Return [(platform_key, matched_domain)] for network domains found in html."""
    low = html.lower()
    hits: list[tuple[str, str]] = []
    for p in PLATFORMS:
        for d in p.network_domains:
            if d in low:
                hits.append((p.key, d))
                break  # one hit per platform is enough
    return hits


def find_program_links(html: str, base_url: str) -> list[str]:
    """Absolute URLs of on-page links that look like a program page."""
    soup = BeautifulSoup(html, "html.parser")
    host = urlparse(base_url).netloc
    found: list[str] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(" ", strip=True)
        if _PROGRAM_HREF.search(href) or _PROGRAM_TEXT.search(text):
            absolute = urljoin(base_url, href)
            # keep on-site links only
            if urlparse(absolute).netloc in ("", host) and absolute not in seen:
                seen.add(absolute)
                found.append(absolute)
    return found


def _audit_row(account_id, fr: FetchResult, note: str = "") -> dict:
    return {
        "account_id": account_id,
        "url": fr.url,
        "final_url": fr.final_url or "",
        "http_status": fr.status if fr.status is not None else "",
        "error": fr.error or "",
        "note": note,
    }


def detect_from_website(
    *, account_id, account_name: str, domain: str | None, session=None
) -> ScrapeOutcome:
    """Probe a brand's website and return a Signal + fetch audit rows."""
    sess = session or make_session()
    fetches: list[dict] = []

    def signal(has_program, platform, confidence, evidence):
        return Signal(account_id, account_name, domain, has_program, platform,
                      "website_scrape", confidence, evidence)

    if not domain:
        return ScrapeOutcome(signal(None, "unknown", "low", {"reason": "no domain"}))

    base = f"https://{domain}"
    home = fetch(base, session=sess)
    fetches.append(_audit_row(account_id, home, "homepage"))
    if not home.ok:
        return ScrapeOutcome(
            signal(None, "unknown", "low",
                   {"reason": "homepage fetch failed", "error": home.error}),
            fetches,
        )

    # 1. network fingerprint on the homepage -> strongest signal
    nets = scan_networks(home.html)
    if nets:
        plat, dom = nets[0]
        return ScrapeOutcome(
            signal(True, plat, "high",
                   {"network_domain": dom, "found_on": home.final_url or base,
                    "all_networks": nets}),
            fetches,
        )

    # 2. program links on the homepage -> follow the first to confirm/identify
    links = find_program_links(home.html, home.final_url or base)
    if links:
        prog = fetch(links[0], session=sess)
        fetches.append(_audit_row(account_id, prog, "program-link"))
        if prog.ok:
            nets2 = scan_networks(prog.html)
            if nets2:
                plat, dom = nets2[0]
                return ScrapeOutcome(
                    signal(True, plat, "high",
                           {"network_domain": dom, "program_url": prog.final_url or links[0]}),
                    fetches,
                )
        return ScrapeOutcome(
            signal(True, "in_house", "medium",
                   {"program_url": links[0], "via": "homepage link"}),
            fetches,
        )

    # 3. nothing on the homepage -> probe a short list of common paths
    for path in PROGRAM_PATHS[:_PROBE_BUDGET]:
        probe = fetch(base + path, session=sess)
        fetches.append(_audit_row(account_id, probe, f"probe {path}"))
        if probe.ok and _PROGRAM_CONFIRM.search(probe.html):
            nets3 = scan_networks(probe.html)
            if nets3:
                plat, dom = nets3[0]
                return ScrapeOutcome(
                    signal(True, plat, "high",
                           {"network_domain": dom, "program_url": probe.final_url or (base + path)}),
                    fetches,
                )
            return ScrapeOutcome(
                signal(True, "in_house", "medium",
                       {"program_url": probe.final_url or (base + path), "via": "path probe"}),
                fetches,
            )

    # checked and found nothing
    return ScrapeOutcome(
        signal(False, "unknown", "low",
               {"reason": "no network fingerprint or program page found",
                "probed": PROGRAM_PATHS[:_PROBE_BUDGET]}),
        fetches,
    )
