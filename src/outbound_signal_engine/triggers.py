"""Trigger classification + scoring (Milestone 3).

Classifies a news headline into a trigger type and scores it by
    points = type_weight * recency_factor * BASE
The per-account trigger_score is the summed points of its trigger articles,
capped at TRIGGER_SCORE_MAX. This becomes the timing bonus added on top of the
M4 fit score, so a high-opportunity account with fresh news rises to the top.

Classification also acts as the noise filter: a headline that matches no trigger
keyword scores nothing, so generic-company-name noise is dropped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from .domains import name_key
from .news import Article

BASE = 10
TRIGGER_SCORE_MAX = 40

# Trigger types in priority order; first match wins. Weights reflect how useful
# the event is as an outreach hook (budget/change signals rank highest).
TRIGGER_TYPES: list[tuple[str, int, re.Pattern]] = [
    ("funding", 3, re.compile(
        r"\b(raises?|raised|funding|seed round|series [a-e]\b|venture|"
        r"secures?\s+\$|\$[\d.]+\s*(m|b|million|billion)|investment round)\b", re.I)),
    ("acquisition", 3, re.compile(
        r"\b(acquires?|acquired|acquisition|merger|to buy|buys|takeover|"
        r"acquihire)\b", re.I)),
    ("leadership", 2, re.compile(
        r"\b(appoints?|names?\s+new|hires?|joins?\s+as|new (ceo|cfo|cmo|coo|cro)|"
        r"chief\s+\w+\s+officer|head of|vp of|appointment)\b", re.I)),
    ("product_launch", 2, re.compile(
        r"\b(launch(es|ed)?|unveils?|introduc(es|ed)|debuts?|rolls? out|"
        r"new (product|collection|line|app))\b", re.I)),
    ("expansion", 2, re.compile(
        r"\b(expands?|expansion|opens?\s+(a\s+)?(new\s+)?(store|location|office)|"
        r"enters?\s+\w+\s+market|international expansion|new market)\b", re.I)),
    ("partnership", 2, re.compile(
        r"\b(partners?\s+with|partnership|teams?\s+up|collaborat(es|ion)|"
        r"joins?\s+forces|joins\s+\d+%)\b", re.I)),
    ("growth_award", 1, re.compile(
        r"\b(fastest[- ]growing|inc\.?\s*5000|award|named to|recognized|"
        r"milestone|record (sales|revenue|year))\b", re.I)),
    ("earnings", 1, re.compile(
        r"\b(earnings|quarterly results|q[1-4]\s*20\d\d|revenue (up|grew|rose)|"
        r"reports? (record |strong )?(revenue|results))\b", re.I)),
]


@dataclass
class ScoredTrigger:
    trigger_type: str
    title: str
    url: str | None
    published_at: datetime | None
    source: str
    score: int


def classify(title: str) -> str | None:
    """Return the trigger type for a headline, or None if it's not a trigger."""
    for ttype, _weight, pattern in TRIGGER_TYPES:
        if pattern.search(title or ""):
            return ttype
    return None


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower())).strip()


def is_relevant(title: str, company: str) -> bool:
    """Cheap precision filter: the company name must appear in the headline.

    Removes off-target matches (e.g. a Burberry article surfacing for a small
    fashion brand). Matching is suffix-aware ("Whirlpool Corporation" still
    matches a "Whirlpool ..." headline) via name_key. Doesn't resolve true name
    collisions (same name, different entity) — left for human review.
    """
    core = name_key(company) or _norm(company)
    return bool(core) and core in _norm(title)


def _weight(ttype: str) -> int:
    return next(w for t, w, _ in TRIGGER_TYPES if t == ttype)


def recency_factor(published_at: datetime | None, now: datetime) -> float:
    """1.0 for very fresh news, decaying to 0 past ~90 days."""
    if published_at is None:
        return 0.3  # unknown date — assume mildly stale
    days = (now - published_at).days
    if days < 0:
        days = 0
    if days <= 14:
        return 1.0
    if days <= 30:
        return 0.8
    if days <= 60:
        return 0.5
    if days <= 90:
        return 0.3
    return 0.0


def score_article(article: Article, now: datetime) -> ScoredTrigger | None:
    ttype = classify(article.title)
    if not ttype:
        return None
    factor = recency_factor(article.published_at, now)
    if factor == 0.0:
        return None  # too old to matter
    points = round(_weight(ttype) * factor * BASE)
    if points <= 0:
        return None
    return ScoredTrigger(ttype, article.title, article.url,
                         article.published_at, article.source, points)


def score_account(articles: list[Article], now: datetime | None = None,
                  company: str | None = None
                  ) -> tuple[int, list[ScoredTrigger]]:
    """Return (trigger_score capped at MAX, scored triggers sorted strongest-first).

    If `company` is given, headlines that don't mention it are dropped first.
    """
    now = now or datetime.now(timezone.utc)
    if company:
        articles = [a for a in articles if is_relevant(a.title, company)]
    scored = [s for a in articles if (s := score_article(a, now))]
    scored.sort(key=lambda s: (-s.score, s.published_at or datetime.min.replace(tzinfo=timezone.utc)))
    total = min(TRIGGER_SCORE_MAX, sum(s.score for s in scored))
    return total, scored
