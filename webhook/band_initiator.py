"""Create a Band room for a PR and post the opening @ScanAgent message.

Spike C (unverified): exact Band REST endpoint paths and auth scheme TBD.
The assumed API shape below is based on BAND_REST_URL + bearer token.
Adjust _create_room / _post_message if Spike C reveals a different shape.
"""
from __future__ import annotations

import os

import httpx

from shared.band_helpers import format_payload
from shared.context_schema import PRContext


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {os.environ['BAND_SERVICE_API_KEY']}",
        "Content-Type": "application/json",
    }


def _base() -> str:
    return os.environ.get("BAND_REST_URL", "https://api.band.ai").rstrip("/")


def _create_room(room_name: str) -> str:
    """Create (or retrieve existing) Band room. Returns room_id."""
    resp = httpx.post(
        f"{_base()}/v1/rooms",
        headers=_headers(),
        json={"name": room_name},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    # Spike C: adjust key name if different (e.g. "id", "room_id", "channel_id")
    return data.get("room_id") or data.get("id") or data["channel_id"]


def _post_message(room_id: str, content: str) -> None:
    """Post a message to a Band room."""
    resp = httpx.post(
        f"{_base()}/v1/rooms/{room_id}/messages",
        headers=_headers(),
        json={"content": content},
        timeout=15,
    )
    resp.raise_for_status()


def initiate_chain(pr: PRContext) -> str:
    """Create a PR room in Band and fire the opening @ScanAgent message.

    Returns the room_id so the webhook response can log it.
    """
    room_name = f"PR-{pr.pr_number}-deployguard"
    room_id = _create_room(room_name)

    engineer = os.environ.get("ENGINEER_HANDLE", "@engineer")
    opening = (
        f"@ScanAgent New PR #{pr.pr_number} by @{pr.author} targeting `{pr.base_branch}` "
        f"— begin DeployGuard safety review.\n"
        f"Engineer on-call: {engineer}\n"
        f"{format_payload(pr.model_dump())}"
    )
    _post_message(room_id, opening)
    return room_id
