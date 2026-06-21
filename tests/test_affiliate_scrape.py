"""Offline tests for Tier-2 scraping logic (no network).

Exercises the HTML analysis — network-fingerprint scanning and program-link
extraction — with static fixtures.

Run with:  python -m pytest tests/test_affiliate_scrape.py -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from outbound_signal_engine.affiliate_scrape import (  # noqa: E402
    find_program_links,
    scan_networks,
)


def test_scan_networks_finds_impact():
    html = '<a href="https://acme.pxf.io/abc123">deal</a>'
    hits = scan_networks(html)
    assert ("impact", "pxf.io") in hits


def test_scan_networks_finds_cj_and_dedupes_platform():
    html = 'tracking via anrdoezrs.net and also dpbolvw.net'
    hits = scan_networks(html)
    keys = [k for k, _ in hits]
    assert keys.count("cj") == 1  # one hit per platform even if two domains match


def test_scan_networks_empty_when_clean():
    assert scan_networks("<html><body>no affiliates here</body></html>") == []


def test_find_program_links_by_href():
    html = '<a href="/affiliates">Join</a><a href="/about">About</a>'
    links = find_program_links(html, "https://acme.com")
    assert "https://acme.com/affiliates" in links
    assert all("/about" not in u for u in links)


def test_find_program_links_by_anchor_text():
    html = '<a href="/x/y">Become an Ambassador</a>'
    links = find_program_links(html, "https://acme.com")
    assert "https://acme.com/x/y" in links


def test_find_program_links_ignores_offsite():
    html = '<a href="https://other.com/affiliate">x</a>'
    assert find_program_links(html, "https://acme.com") == []
