"""A small, polite HTTP fetcher for Tier-2 scraping.

Deliberately conservative: a descriptive User-Agent, short timeouts, capped
response size, and graceful failure (errors are returned, never raised). The
goal is to read a brand's public homepage and a couple of program pages — not
to crawl — so we keep the footprint tiny.
"""

from __future__ import annotations

from dataclasses import dataclass

import requests

USER_AGENT = (
    "outbound-signal-engine/0.1 "
    "(+https://github.com/jbailey28/outbound-signal-engine; research)"
)
DEFAULT_TIMEOUT = 10  # seconds
MAX_BYTES = 2_000_000  # don't read more than ~2 MB of HTML


@dataclass
class FetchResult:
    url: str               # url requested
    final_url: str | None  # url after redirects
    status: int | None
    html: str | None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status is not None and 200 <= self.status < 300 and self.html is not None


def fetch(url: str, *, timeout: int = DEFAULT_TIMEOUT, session: requests.Session | None = None) -> FetchResult:
    """GET a URL politely. Returns a FetchResult; never raises for network errors."""
    s = session or requests
    try:
        resp = s.get(
            url,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"},
            allow_redirects=True,
            stream=True,
        )
        ctype = resp.headers.get("Content-Type", "")
        if "html" not in ctype and "xml" not in ctype and ctype:
            resp.close()
            return FetchResult(url, str(resp.url), resp.status_code, None,
                               error=f"non-html content-type: {ctype}")
        # cap how much we read
        content = resp.raw.read(MAX_BYTES, decode_content=True)
        resp.close()
        html = content.decode(resp.encoding or "utf-8", errors="replace")
        return FetchResult(url, str(resp.url), resp.status_code, html)
    except requests.RequestException as e:
        return FetchResult(url, None, None, None, error=type(e).__name__ + ": " + str(e)[:200])


def make_session() -> requests.Session:
    """A reusable session (connection pooling) for a batch of fetches."""
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s
