"""Spike A — verify a single Band agent connects, receives an @mention, and replies.

This is the gate for the whole project: it confirms the WebSocket connection, the
LangGraph adapter, and LLM tool-calling all work end to end before any feature code.

Run:
    1. Fill SCAN_AGENT_ID / SCAN_AGENT_API_KEY and FEATHERLESS_* in .env
       (any registered agent works; we reuse the 'scan' slot here).
    2. python -m spike.spike_a_echo_agent
    3. In Band, @mention the agent and confirm it replies.

If this hangs or errors, fix connectivity/credentials/model before building agents.
Also use this to confirm Spike B: does LangGraphAdapter actually accept
`tools=` and `system_prompt=`? Adjust shared/agent_runner.build_adapter if not.
"""

from __future__ import annotations

from dotenv import load_dotenv

# A trivial custom tool — proves tool-calling reaches our code (Spike B).
try:
    from langchain_core.tools import tool
except Exception:  # pragma: no cover - import guard for environments w/o langchain
    tool = None


SYSTEM_PROMPT = (
    "You are a connectivity test agent for DeployGuard. When mentioned, call the "
    "`echo` tool with a short confirmation string, then reply in the room with the "
    "result so we can confirm tool-calling works."
)


def _build_tools() -> list:
    if tool is None:
        return []

    @tool
    def echo(message: str) -> str:
        """Echo a message back to confirm the tool path is wired."""
        return f"echo: {message}"

    return [echo]


def main() -> None:
    load_dotenv()
    # Imported here so the module is importable even before deps are installed.
    import asyncio

    from shared.agent_runner import run_agent

    asyncio.run(run_agent("scan", SYSTEM_PROMPT, _build_tools()))


if __name__ == "__main__":
    main()
