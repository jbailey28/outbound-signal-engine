#!/usr/bin/env python3
"""Generate first-touch email DRAFTS for the top-ranked prospects (Milestone 5).

Pulls the highest-scoring accounts from Supabase (segment + top trigger),
renders a first-touch draft from your templates, and writes one .txt per draft
plus a combined CSV. DRAFTS ONLY — nothing is sent.

Usage:
    python scripts/generate_drafts.py --top 5
    python scripts/generate_drafts.py --config data/reference/email_config.json --top 10

Config: defaults to data/reference/email_config.json (your real, gitignored
config); falls back to the committed sample if that's missing.
Needs SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY in .env.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from outbound_signal_engine.emails import generate_draft, load_config  # noqa: E402
from outbound_signal_engine.supabase_loader import (  # noqa: E402
    fetch_prospects_for_drafts,
    make_client,
)

DEFAULT_CONFIG = "data/reference/email_config.json"
SAMPLE_CONFIG = "data/sample/email_config.sample.json"
STYLE_GUIDE_PATH = "data/reference/sample_messaging.txt"


def _load_style_guide(config: dict) -> str:
    """Few-shot style for the LLM: the rep's real emails if present, else templates."""
    p = Path(STYLE_GUIDE_PATH)
    if p.exists():
        return p.read_text()
    return "\n\n".join(config.get("templates", {}).values())


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--config", default=None, help="email config JSON path")
    ap.add_argument("--top", type=int, default=5, help="how many drafts (default 5)")
    ap.add_argument("--include-customers", action="store_true",
                    help="also draft for existing_customer accounts (normally skipped)")
    ap.add_argument("--provider", choices=["template", "claude", "ollama"], default=None,
                    help="draft generator: template (default, free), claude (Anthropic API), "
                         "ollama (local, free)")
    ap.add_argument("--llm", action="store_true", help="alias for --provider claude")
    args = ap.parse_args()
    provider = args.provider or ("claude" if args.llm else "template")

    config_path = args.config or (DEFAULT_CONFIG if Path(DEFAULT_CONFIG).exists() else SAMPLE_CONFIG)
    if not Path(config_path).exists():
        print(f"error: config not found: {config_path}\n"
              f"       copy {SAMPLE_CONFIG} to {DEFAULT_CONFIG} and edit it.", file=sys.stderr)
        return 1
    config = load_config(config_path)
    print(f"using config: {config_path}  (sender: {config.get('sender')}, platform: {config.get('platform')})")

    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("error: set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env", file=sys.stderr)
        return 1

    client = make_client(url, key)
    prospects = fetch_prospects_for_drafts(client)
    if not args.include_customers:
        prospects = [p for p in prospects if p["segment"] != "existing_customer"]
    prospects = prospects[:args.top]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path("data/output") / f"drafts__{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "_drafts.csv"

    # Build the chosen LLM generator (a closure taking a prospect dict). None = template.
    llm_generate = None
    if provider != "template":
        style_guide = _load_style_guide(config)
        if provider == "claude":
            if not os.environ.get("ANTHROPIC_API_KEY"):
                print("error: --provider claude needs ANTHROPIC_API_KEY in .env", file=sys.stderr)
                return 1
            from anthropic import Anthropic
            from outbound_signal_engine.emails_llm import DEFAULT_MODEL, generate_draft_llm
            client = Anthropic()
            model = os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL
            llm_generate = lambda p: generate_draft_llm(  # noqa: E731
                account_id=p["account_id"], account_name=p["account_name"], segment=p["segment"],
                industry=p.get("industry"), sub_industry=p.get("sub_industry"),
                trigger_type=p.get("top_trigger_type"), trigger_title=p.get("top_trigger_title"),
                config=config, style_guide=style_guide, client=client)
        else:  # ollama
            from outbound_signal_engine.emails_ollama import DEFAULT_MODEL, generate_draft_ollama
            model = os.environ.get("OLLAMA_MODEL") or DEFAULT_MODEL
            llm_generate = lambda p: generate_draft_ollama(  # noqa: E731
                account_id=p["account_id"], account_name=p["account_name"], segment=p["segment"],
                industry=p.get("industry"), sub_industry=p.get("sub_industry"),
                trigger_type=p.get("top_trigger_type"), trigger_title=p.get("top_trigger_title"),
                config=config, style_guide=style_guide)
        print(f"generating with {provider} ({model}); falling back to templates on error")

    rows = []
    for i, p in enumerate(prospects, start=1):
        d = None
        if llm_generate is not None:
            try:
                d = llm_generate(p)
            except Exception as e:  # noqa: BLE001 — fall back so one bad call doesn't kill the run
                print(f"  ! {provider} failed for {p['account_name']} ({e}); using template",
                      file=sys.stderr)
        if d is None:
            d = generate_draft(
                account_id=p["account_id"], account_name=p["account_name"],
                segment=p["segment"], industry=p.get("industry"),
                sub_industry=p.get("sub_industry"), trigger_type=p.get("top_trigger_type"),
                config=config,
            )
        slug = re.sub(r"[^a-z0-9]+", "-", p["account_name"].lower()).strip("-")[:40]
        (out_dir / f"{i:02d}_{slug}.txt").write_text(
            f"To: {p['account_name']} ({p.get('domain') or ''})\n"
            f"Segment: {d.segment} | Score: {p['total_score']} | "
            f"Trigger: {p.get('top_trigger_type') or 'none'}\n"
            f"Subject: {d.subject}\n\n{d.body}\n"
        )
        rows.append({
            "rank": i, "account_name": p["account_name"], "domain": p.get("domain") or "",
            "segment": d.segment, "template": d.template, "score": p["total_score"],
            "trigger_type": p.get("top_trigger_type") or "", "used_trigger": d.used_trigger,
            "subject": d.subject, "body": d.body,
        })

    with open(csv_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["rank"])
        w.writeheader()
        w.writerows(rows)

    # preview the top 2 in the terminal
    for r in rows[:2]:
        print("\n" + "=" * 64)
        print(f"  #{r['rank']}  {r['account_name']}  [{r['segment']}, score {r['score']}, "
              f"trigger: {r['trigger_type'] or 'none'}]")
        print(f"  Subject: {r['subject']}")
        print("-" * 64)
        print(r["body"])
    print("\n" + "=" * 64)
    print(f"  {len(rows)} drafts written -> {out_dir}/")
    print("  DRAFTS ONLY — review and edit before sending. Fill {{first_name}} per contact.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
