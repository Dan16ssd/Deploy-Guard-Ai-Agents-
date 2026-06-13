"""Single Band SDK bootstrap reused by all five agents.

Each agents/*.py supplies only its identity key, system prompt, and tool list;
this module wires the LangGraph adapter, the LLM (from llm_factory), and the Band
connection, then runs the agent's WebSocket loop.

NOTE (Spike B): the exact LangGraphAdapter signature for attaching custom tools and
a system prompt is unverified against band-sdk 1.0.0 (docs are gated). The call below
reflects the assumed API; `build_adapter` is isolated so that, once Spike B confirms
the real signature, this is the only function that changes.
"""
from __future__ import annotations

import asyncio
from typing import Any, Sequence

from .llm_factory import build_llm, resolve_credentials


def build_adapter(agent_key: str, system_prompt: str, tools: Sequence[Any]) -> Any:
    """Construct the LangGraphAdapter for an agent. (Spike B: confirm signature.)"""
    from band.adapters import LangGraphAdapter
    from langgraph.checkpoint.memory import InMemorySaver

    llm = build_llm(agent_key)
    return LangGraphAdapter(
        llm=llm,
        checkpointer=InMemorySaver(),
        tools=list(tools),
        system_prompt=system_prompt,
    )


async def run_agent(
    agent_key: str,
    system_prompt: str,
    tools: Sequence[Any],
) -> None:
    """Create and run a Band agent until cancelled."""
    from band import Agent

    agent_id, api_key = resolve_credentials(agent_key)
    adapter = build_adapter(agent_key, system_prompt, tools)
    agent = Agent.create(adapter=adapter, agent_id=agent_id, api_key=api_key)
    await agent.run()


def main(agent_key: str, system_prompt: str, tools: Sequence[Any]) -> None:
    """Synchronous entrypoint for `python -m agents.<name>`."""
    from dotenv import load_dotenv

    load_dotenv()
    try:
        asyncio.run(run_agent(agent_key, system_prompt, tools))
    except KeyboardInterrupt:
        pass
