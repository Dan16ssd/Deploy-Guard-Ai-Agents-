"""Helpers for parsing and composing Band @mention messages.

Agents pass structured payloads to each other by embedding a fenced JSON block in
the message body. These helpers extract @mentions, pull the JSON back out, and
detect human decision keywords (APPROVE/REJECT/OVERRIDE/FIX).
"""

from __future__ import annotations

import json
import re
from typing import Any

from .verdict import HumanDecision

_MENTION_RE = re.compile(r"@([A-Za-z0-9_\-]+)")
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def extract_mentions(text: str) -> list[str]:
    """Return agent/user handles mentioned in a message (without the leading @)."""
    return _MENTION_RE.findall(text or "")


def extract_json_payload(text: str) -> dict[str, Any] | None:
    """Pull the first fenced JSON block out of a message body, if present.

    Falls back to a bare top-level JSON object if no code fence is used.
    """
    if not text:
        return None
    match = _JSON_BLOCK_RE.search(text)
    candidate = match.group(1) if match else None
    if candidate is None:
        brace = text.find("{")
        if brace != -1:
            candidate = text[brace:]
    if not candidate:
        return None
    try:
        return json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return None


def format_payload(payload: dict[str, Any]) -> str:
    """Render a payload as a fenced JSON block for embedding in a message."""
    return "```json\n" + json.dumps(payload, indent=2, default=str) + "\n```"


def compose_handoff(mention: str, summary: str, payload: dict[str, Any]) -> str:
    """Build a hand-off message: '@Next <summary>\n<json>'."""
    handle = mention if mention.startswith("@") else f"@{mention}"
    return f"{handle} {summary}\n{format_payload(payload)}"


def detect_human_decision(text: str) -> HumanDecision | None:
    """Identify an APPROVE/REJECT/OVERRIDE/FIX keyword in a human reply."""
    if not text:
        return None
    upper = text.upper()
    # Order matters: check explicit gate words first.
    for word in ("APPROVE", "REJECT", "OVERRIDE", "FIX"):
        if re.search(rf"\b{word}\b", upper):
            return HumanDecision(word)
    return None
