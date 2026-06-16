"""Create a Band chat for a PR and post the opening @ScanAgent message.

Spike C (verified against thenvoi-client-rest 0.0.7 / band-sdk 1.0.0): the webhook
acts as a Band *service agent*. Using the real generated REST client it:
  1. creates a chat        -> agent_api_chats.create_agent_chat(ChatRoomRequest)
  2. adds the chain agents -> agent_api_participants.add_agent_chat_participant(...)
  3. posts the opener      -> agent_api_messages.create_agent_chat_message(
                                 ChatMessageRequest(content, mentions=[...ScanAgent]))

Participant-adding is best-effort: depending on Band's contact model it may require
the service agent to already have the chain agents as peers. A failure there does not
abort chat creation / the opening message.
"""

from __future__ import annotations

import os

from band.client.rest import (
    ChatMessageRequest,
    ChatMessageRequestMentionsItem,
    ChatRoomRequest,
    ParticipantRequest,
    RestClient,
)

from shared.band_helpers import format_payload
from shared.context_schema import PRContext

# (env var holding the Band agent id, display handle) for each chain agent.
_AGENTS: list[tuple[str, str]] = [
    ("SCAN_AGENT_ID", "ScanAgent"),
    ("SECURITY_AGENT_ID", "SecurityAgent"),
    ("RISK_AGENT_ID", "RiskAgent"),
    ("DEPLOY_AGENT_ID", "DeployAgent"),
    ("REPORT_AGENT_ID", "ReportAgent"),
]


def _client() -> RestClient:
    api_key = os.environ["BAND_SERVICE_API_KEY"]
    base_url = os.environ.get("BAND_REST_URL", "https://app.band.ai").rstrip("/")
    return RestClient(api_key=api_key, base_url=base_url)


def _agent_ids() -> dict[str, str]:
    """Resolve {handle: agent_id} for agents whose id is configured in env."""
    return {
        handle: os.environ[env_name]
        for env_name, handle in _AGENTS
        if os.environ.get(env_name)
    }


def initiate_chain(pr: PRContext) -> str:
    """Create a Band chat for the PR and fire the opening @ScanAgent message.

    Returns the chat id so the webhook response can log it.
    """
    client = _client()
    ids = _agent_ids()

    # task_id, if provided, must be a UUID — we don't have one per PR, so omit it.
    # The PR identity lives in the opening message content below.
    chat = client.agent_api_chats.create_agent_chat(chat=ChatRoomRequest())
    chat_id = chat.data.id

    # Add every chain agent as a participant so @mentions reach them (best-effort).
    for handle, agent_id in ids.items():
        try:
            client.agent_api_participants.add_agent_chat_participant(
                chat_id,
                participant=ParticipantRequest(participant_id=agent_id, role="member"),
            )
        except Exception as exc:  # noqa: BLE001 - resilience over strictness here
            print(f"[band_initiator] could not add {handle} to chat {chat_id}: {exc}")

    # Add the on-call engineer (a human User) so BLOCK/ESCALATE @mentions reach them.
    # Resolve their participant id by handle from the service identity's peer list so we
    # don't hard-code a user id. ENGINEER_HANDLE is like "@danny.ssd7".
    eng_username = os.environ.get("ENGINEER_HANDLE", "").lstrip("@")
    if eng_username:
        try:
            peers = client.agent_api_peers.list_agent_peers()
            for peer in getattr(peers, "data", []) or []:
                if getattr(peer, "handle", None) == eng_username:
                    client.agent_api_participants.add_agent_chat_participant(
                        chat_id,
                        participant=ParticipantRequest(
                            participant_id=peer.id, role="member"
                        ),
                    )
                    break
        except Exception as exc:  # noqa: BLE001 - resilience over strictness here
            print(f"[band_initiator] could not add engineer {eng_username}: {exc}")

    engineer = os.environ.get("ENGINEER_HANDLE", "@engineer")
    content = (
        f"@ScanAgent New PR #{pr.pr_number} by @{pr.author} targeting "
        f"`{pr.base_branch}` — begin DeployGuard safety review.\n"
        f"Engineer on-call: {engineer}\n"
        f"{format_payload(pr.model_dump())}"
    )

    mentions: list[ChatMessageRequestMentionsItem] = []
    if scan_id := ids.get("ScanAgent"):
        mentions.append(
            ChatMessageRequestMentionsItem(
                id=scan_id, handle="ScanAgent", name="ScanAgent"
            )
        )

    client.agent_api_messages.create_agent_chat_message(
        chat_id,
        message=ChatMessageRequest(content=content, mentions=mentions),
    )
    return chat_id
