"""URL -> clean domain normalization.

The domain is our primary deduplication key, so this needs to be consistent and
predictable. We deliberately keep it dependency-free (no tldextract / no network)
so the import is reproducible offline. The trade-off: multi-part public suffixes
like `.co.uk` are handled with a small built-in list rather than a full suffix
database. That covers the vast majority of B2B account books; extend
`MULTI_PART_TLDS` if your book skews toward a region this misses.
"""

from __future__ import annotations

from urllib.parse import urlparse

# Common multi-part public suffixes. Not exhaustive — extend as needed.
MULTI_PART_TLDS = {
    "co.uk", "org.uk", "ac.uk", "gov.uk", "me.uk",
    "com.au", "net.au", "org.au", "gov.au",
    "co.nz", "co.za", "com.br", "com.mx", "com.sg",
    "co.jp", "or.jp", "co.in", "co.kr", "com.cn",
}


def clean_url(raw: str | None) -> str | None:
    """Return a canonical https URL (scheme + host), or None if unusable.

    >>> clean_url("WWW.Example.com/partners?utm=x")
    'https://example.com'
    >>> clean_url("http://shop.example.co.uk")
    'https://shop.example.co.uk'
    """
    domain = normalize_domain(raw)
    if not domain:
        return None
    return f"https://{domain}"


def normalize_domain(raw: str | None) -> str | None:
    """Reduce any URL-ish string to its registrable domain (lowercase).

    Strips scheme, `www.`, port, path, query, and fragment, then collapses the
    host to its registrable part (e.g. `blog.shop.example.com` -> `example.com`,
    `example.co.uk` -> `example.co.uk`). Returns None for empty/invalid input.

    >>> normalize_domain("https://www.Example.com/affiliates")
    'example.com'
    >>> normalize_domain("sub.example.co.uk")
    'example.co.uk'
    >>> normalize_domain("not a url")
    >>> normalize_domain("")
    """
    host = _extract_host(raw)
    if not host:
        return None
    return _registrable_domain(host)


def _extract_host(raw: str | None) -> str | None:
    if not raw:
        return None
    value = raw.strip().lower()
    if not value or " " in value.strip():
        # Reject obviously non-URL free text ("not a url", "n/a", etc.),
        # but allow leading/trailing space which we've already stripped.
        value = value.strip()
        if " " in value:
            return None
    if not value:
        return None

    # urlparse needs a scheme to populate netloc; add one if missing.
    if "://" not in value:
        value = "//" + value
    netloc = urlparse(value).netloc or ""
    # drop credentials and port
    netloc = netloc.split("@")[-1].split(":")[0]
    if netloc.startswith("www."):
        netloc = netloc[4:]

    # A real host must contain a dot and a letter (filters "n/a", "tbd", etc.).
    if "." not in netloc or not any(c.isalpha() for c in netloc):
        return None
    return netloc.strip(".") or None


def _registrable_domain(host: str) -> str:
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    last_two = ".".join(parts[-2:])
    if last_two in MULTI_PART_TLDS:
        return ".".join(parts[-3:])
    return last_two


def name_key(account_name: str | None) -> str:
    """Normalized account-name key used as the fallback dedup key.

    Lowercases, strips common company suffixes and punctuation so that
    "Acme, Inc." and "Acme Inc" collapse to the same key.

    >>> name_key("Acme, Inc.")
    'acme'
    >>> name_key("  Globex   Corporation ")
    'globex'
    """
    if not account_name:
        return ""
    value = account_name.lower()
    # replace punctuation with spaces
    value = "".join(c if c.isalnum() or c.isspace() else " " for c in value)
    tokens = value.split()
    suffixes = {
        "inc", "llc", "ltd", "limited", "corp", "corporation", "co",
        "company", "plc", "gmbh", "sa", "ag", "group", "holdings",
    }
    tokens = [t for t in tokens if t not in suffixes]
    return " ".join(tokens).strip()
