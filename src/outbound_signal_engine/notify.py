"""Post the daily drafts to a Discord channel via an incoming webhook.

Discord caps a message at 2000 characters, so each draft is sent as its own
message (chunked further if a single draft is unusually long), preceded by a
short summary line. No bot, no OAuth — just the webhook URL in .env.
"""

from __future__ import annotations

import time

import requests

_MAX = 1900  # stay under Discord's 2000-char hard limit


def format_draft(rank: int, row: dict) -> str:
    """Render one draft row as a Discord message (markdown)."""
    return (
        f"**{rank}. {row['account_name']}** — {row['segment']} · "
        f"score {row['score']} · trigger: {row.get('trigger_type') or 'none'}\n"
        f"🌐 {row.get('website') or '—'}   📸 {row.get('instagram') or '—'}\n"
        f"**Subject:** {row['subject']}\n"
        f"```\n{row['body']}\n```"
    )


def _chunks(text: str, size: int = _MAX) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)] or [""]


def post_drafts(webhook_url: str, date_str: str, rows: list[dict],
                *, session: requests.Session | None = None) -> int:
    """Post a header + one message per draft. Returns the number of messages sent."""
    s = session or requests.Session()
    sent = 0

    def _send(content: str) -> None:
        nonlocal sent
        r = s.post(webhook_url, json={"content": content}, timeout=15)
        r.raise_for_status()
        sent += 1
        time.sleep(0.4)  # gentle pacing under Discord's rate limit

    _send(f"📬 **Your {len(rows)} accounts for {date_str}** — drafts to review & edit "
          "(fill in each contact's first name).")
    for rank, row in enumerate(rows, start=1):
        for chunk in _chunks(format_draft(rank, row)):
            _send(chunk)
    return sent
