"""Find a company's social links from its homepage (best-effort, no new deps).

Used to surface an Instagram link in the draft header so the rep can manually
scan for triggers we didn't auto-detect. We extract the real profile link a
brand puts in its own footer; if none is found, we return a Google search link
so there's always a one-click entry point.

Instagram is intentionally NOT scraped for triggers — it's login-walled, blocks
bots, and its ToS prohibits it. This is a human-in-the-loop convenience only.
"""

from __future__ import annotations

import re
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

# Path segments that are not profile handles.
_IG_NON_HANDLES = {
    "p", "reel", "reels", "explore", "accounts", "about", "developer",
    "developers", "directory", "legal", "privacy", "tv", "stories", "",
}
_IG_RE = re.compile(r"instagram\.com/([A-Za-z0-9_.]+)", re.I)


def extract_instagram(html: str) -> str | None:
    """Return the brand's Instagram profile URL from homepage HTML, or None."""
    soup = BeautifulSoup(html or "", "html.parser")
    for a in soup.find_all("a", href=True):
        m = _IG_RE.search(a["href"])
        if not m:
            continue
        handle = m.group(1).strip("/").lower()
        if handle and handle not in _IG_NON_HANDLES:
            return f"https://www.instagram.com/{handle}"
    return None


def instagram_search_url(company: str) -> str:
    """Fallback: a Google search that lands on the company's Instagram."""
    return "https://www.google.com/search?q=" + quote_plus(f"{company} instagram")
