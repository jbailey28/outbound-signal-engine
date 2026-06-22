"""Local LLM draft generation via Ollama (free, offline, no API key).

A second backend for M5's LLM drafts. Reuses the exact same prompt assembly as
the Claude path (`emails_llm.build_prompt`) — only the inference call differs —
so the rep's voice, the safety rules, and the {{first_name}} placeholder behave
identically whichever model runs.

Ollama runs models locally (https://ollama.com). Nothing leaves the machine and
there's no per-draft cost — a good fit for a tool handling account data.

Setup:
    1. install Ollama, then `ollama pull llama3.1` (or any chat model)
    2. set OLLAMA_MODEL in .env (default: llama3.1)
       OLLAMA_BASE_URL defaults to http://localhost:11434

Works with any OpenAI-/Ollama-compatible local server (LM Studio, vLLM, …) that
speaks Ollama's /api/chat — point OLLAMA_BASE_URL at it.
"""

from __future__ import annotations

import os
from typing import Any

import requests

from .emails import Draft
from .emails_llm import build_prompt, parse_subject_body

DEFAULT_MODEL = "llama3.1"
DEFAULT_BASE_URL = "http://localhost:11434"

# Ollama structured-output schema (newer Ollama supports `format` as a JSON schema).
_FORMAT = {
    "type": "object",
    "properties": {"subject": {"type": "string"}, "body": {"type": "string"}},
    "required": ["subject", "body"],
}


def generate_draft_ollama(
    *,
    account_id: str | None,
    account_name: str,
    segment: str,
    industry: str | None,
    sub_industry: str | None,
    trigger_type: str | None,
    trigger_title: str | None,
    config: dict[str, Any],
    style_guide: str,
    model: str | None = None,
    base_url: str | None = None,
    timeout: int = 120,
) -> Draft:
    """Generate a draft with a local Ollama model. Raises on connection/parse error
    so the caller can fall back to the template generator."""
    model = model or os.environ.get("OLLAMA_MODEL") or DEFAULT_MODEL
    base = (base_url or os.environ.get("OLLAMA_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    system, user = build_prompt(
        account_name=account_name, segment=segment, industry=industry,
        sub_industry=sub_industry, trigger_type=trigger_type, trigger_title=trigger_title,
        config=config, style_guide=style_guide,
    )

    resp = requests.post(
        f"{base}/api/chat",
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "format": _FORMAT,
            "options": {"temperature": 0.7},
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    content = resp.json()["message"]["content"]
    data = parse_subject_body(content)

    return Draft(
        account_id=account_id,
        account_name=account_name,
        segment=segment,
        template="ollama",
        subject=data["subject"],
        body=data["body"],
        used_trigger=bool(trigger_type and trigger_title),
    )
