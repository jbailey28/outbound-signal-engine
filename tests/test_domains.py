"""Tests for domain normalization and dedup keys.

Run with:  python -m pytest tests/test_domains.py -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from outbound_signal_engine.domains import (  # noqa: E402
    clean_url,
    name_key,
    normalize_domain,
)


def test_normalize_basic():
    assert normalize_domain("https://www.Example.com/affiliates") == "example.com"
    assert normalize_domain("HTTP://Example.COM") == "example.com"
    assert normalize_domain("example.com") == "example.com"


def test_normalize_strips_subdomain():
    assert normalize_domain("blog.shop.example.com") == "example.com"
    assert normalize_domain("www.example.com") == "example.com"


def test_normalize_multi_part_tld():
    assert normalize_domain("sub.example.co.uk") == "example.co.uk"
    assert normalize_domain("example.com.au") == "example.com.au"


def test_normalize_strips_port_and_query():
    assert normalize_domain("https://example.com:8080/x?y=1#z") == "example.com"


def test_normalize_rejects_junk():
    assert normalize_domain("") is None
    assert normalize_domain(None) is None
    assert normalize_domain("n/a") is None
    assert normalize_domain("not a url") is None
    assert normalize_domain("TBD") is None


def test_clean_url():
    assert clean_url("WWW.Example.com/partners?utm=x") == "https://example.com"
    assert clean_url("shop.example.co.uk") == "https://example.co.uk"
    assert clean_url("") is None


def test_name_key():
    assert name_key("Acme, Inc.") == "acme"
    assert name_key("  Globex   Corporation ") == "globex"
    assert name_key("Initech LLC") == "initech"
    assert name_key("Acme Inc") == name_key("Acme, Inc.")
