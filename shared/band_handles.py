"""Resolve Band @mention handles for the chain agents and the on-call engineer.

Band agent handles are `<username>/<agentname-lowercased>` (e.g. danny.ssd7/securityagent),
and the human handle is just `<username>`. We derive `<username>` from ENGINEER_HANDLE
(or BAND_USERNAME if set) so nothing is hard-coded to one account.

These handles go into `band_send_message(content, mentions=[...])` — the only way a Band
agent can actually deliver a message (plain text output is dropped by the platform).
"""

from __future__ import annotations

import os

# Agent modules compute their hand-off handles at IMPORT time (module-level constants),
# which runs before agent_runner.main() calls load_dotenv(). Load the .env here so the
# username resolves to the real account (e.g. danny.ssd7) instead of the "@engineer"
# fallback — otherwise every band_send_message mention is an unknown participant and no
# hand-off is ever delivered.
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


def username() -> str:
    explicit = os.environ.get("BAND_USERNAME")
    if explicit:
        return explicit.lstrip("@")
    return os.environ.get("ENGINEER_HANDLE", "@engineer").lstrip("@")


def agent_handle(agent_name: str) -> str:
    """e.g. agent_handle("SecurityAgent") -> "@danny.ssd7/securityagent"."""
    return f"@{username()}/{agent_name.lower()}"


def engineer_handle() -> str:
    """The human on-call handle for escalations/blocks, e.g. "@danny.ssd7"."""
    return f"@{username()}"
