"""News sources for Tier-3 trigger detection.

A small pluggable layer: a `NewsSource` yields recent `Article`s for a company.
Google News RSS is implemented (free, no key). The two query *strategies* —
broad and trigger-targeted — give both recall and precision from one provider;
a second provider (NewsAPI, Claude web search) can be added by implementing the
same interface.
"""

from __future__ import annotations

import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from .web import make_session

# Terms that bias a query toward actual trigger events (the "targeted" strategy).
TRIGGER_QUERY_TERMS = (
    "raises OR funding OR acquires OR acquisition OR merger OR launches OR "
    "unveils OR hires OR appoints OR expands OR partnership OR \"series\""
)


@dataclass
class Article:
    title: str
    url: str | None
    published_at: datetime | None
    source: str  # which strategy/provider surfaced it


def _parse_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        return None


class GoogleNewsRSS:
    """Free Google News RSS search. No API key."""

    name = "google_news"

    def __init__(self, session=None):
        self.session = session or make_session()

    def _query(self, q: str, strategy: str, limit: int) -> list[Article]:
        url = (
            "https://news.google.com/rss/search?q="
            + urllib.parse.quote(q)
            + "&hl=en-US&gl=US&ceid=US:en"
        )
        try:
            resp = self.session.get(url, timeout=15)
            root = ET.fromstring(resp.content)
        except Exception:
            return []
        out: list[Article] = []
        for item in root.findall(".//item")[:limit]:
            out.append(Article(
                title=(item.findtext("title") or "").strip(),
                url=item.findtext("link"),
                published_at=_parse_date(item.findtext("pubDate")),
                source=f"{self.name}:{strategy}",
            ))
        return out

    def search(self, company: str, *, limit: int = 10) -> list[Article]:
        """Run both the broad and trigger-targeted strategies, merged + deduped."""
        broad = self._query(f'"{company}"', "broad", limit)
        targeted = self._query(f'"{company}" ({TRIGGER_QUERY_TERMS})', "targeted", limit)
        return dedupe(broad + targeted)


def dedupe(articles: list[Article]) -> list[Article]:
    """Drop duplicate articles by URL, then by normalized title."""
    seen: set[str] = set()
    out: list[Article] = []
    for a in articles:
        key = (a.url or "").split("?")[0] or a.title.lower().strip()
        if key and key not in seen:
            seen.add(key)
            out.append(a)
    return out
