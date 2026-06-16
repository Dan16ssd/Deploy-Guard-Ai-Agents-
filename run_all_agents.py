"""Run all five DeployGuard agents in a single process.

Railway (and similar PaaS) cap the number of services on smaller plans, and six boxes
(webhook + 5 agents) blows past that. This module runs all five agents concurrently in one
service instead, so the whole chain needs just two services: the webhook + this runner.

Each agent gets its own asyncio task under an independent supervisor: if one agent crashes
(bad model response, Band hiccup, Featherless 429, …) only that agent restarts — the other
four keep running. This is deliberately more resilient than five separate Railway services,
where a crash-looping box just sits dead until someone notices.

Start command (Railway "Custom Start Command", or locally):
    python -m run_all_agents
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any, Sequence

from dotenv import load_dotenv

from agents import (
    deploy_agent,
    report_agent,
    risk_agent,
    scan_agent,
    security_agent,
)
from shared.agent_runner import run_agent

# (agent_key, system prompt, tools) for every agent in the chain.
AGENTS: list[tuple[str, str, Sequence[Any]]] = [
    ("scan", scan_agent.SYSTEM_PROMPT, scan_agent.TOOLS),
    ("security", security_agent.SYSTEM_PROMPT, security_agent.TOOLS),
    ("risk", risk_agent.SYSTEM_PROMPT, risk_agent.TOOLS),
    ("deploy", deploy_agent.SYSTEM_PROMPT, deploy_agent.TOOLS),
    ("report", report_agent.SYSTEM_PROMPT, report_agent.TOOLS),
]

# Backoff between restarts of a single agent so a hard-failing one doesn't hot-loop.
RESTART_BACKOFF_SECONDS = 5.0


async def _supervise(agent_key: str, system_prompt: str, tools: Sequence[Any]) -> None:
    """Run one agent forever, restarting it on any crash without disturbing the others."""
    while True:
        try:
            # run_agent already retries transient Band WebSocket drops internally; this outer
            # loop catches anything that still escapes (e.g. a hard crash) and cold-restarts.
            await run_agent(agent_key, system_prompt, tools, reconnect_retries=5)
            print(f"[{agent_key}] run_agent returned; restarting.", file=sys.stderr, flush=True)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — supervisor must never propagate
            print(
                f"[{agent_key}] crashed with {type(exc).__name__}: {exc} — "
                f"restarting in {RESTART_BACKOFF_SECONDS:.0f}s",
                file=sys.stderr,
                flush=True,
            )
        await asyncio.sleep(RESTART_BACKOFF_SECONDS)


async def main() -> None:
    load_dotenv()
    print(
        f"[run_all_agents] starting {len(AGENTS)} agents: "
        f"{', '.join(k for k, _, _ in AGENTS)}",
        file=sys.stderr,
        flush=True,
    )
    await asyncio.gather(*(_supervise(k, p, t) for k, p, t in AGENTS))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
