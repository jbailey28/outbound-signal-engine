"""Offline tests for homepage social-link extraction."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from outbound_signal_engine.socials import extract_instagram, instagram_search_url  # noqa: E402


def test_extract_profile_link():
    html = '<footer><a href="https://www.instagram.com/acmebrand/">IG</a></footer>'
    assert extract_instagram(html) == "https://www.instagram.com/acmebrand"


def test_skips_post_and_picks_profile():
    html = (
        '<a href="https://instagram.com/p/abc123/">a post</a>'
        '<a href="http://instagram.com/realbrand">profile</a>'
    )
    assert extract_instagram(html) == "https://www.instagram.com/realbrand"


def test_returns_none_when_no_instagram():
    assert extract_instagram('<a href="https://twitter.com/x">tw</a>') is None
    assert extract_instagram("") is None


def test_search_fallback_url():
    url = instagram_search_url("Acme & Co")
    assert url.startswith("https://www.google.com/search?q=")
    assert "Acme" in url and "instagram" in url
