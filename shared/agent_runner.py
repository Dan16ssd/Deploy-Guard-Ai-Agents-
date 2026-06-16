"""Single Band SDK bootstrap reused by all five agents.

Each agents/*.py supplies only its identity key, system prompt, and tool list;
this module wires the LangGraph adapter, the LLM (from llm_factory), and the Band
connection, then runs the agent's WebSocket loop.

Spike B (verified against band-sdk 1.0.0): the LangGraphAdapter takes the tool list
as `additional_tools=` and the per-agent instructions as `custom_section=` (there is
no `system_prompt=` arg). `build_adapter` is the single place this wiring lives.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Sequence, Union

from .llm_factory import build_llm, resolve_credentials

# Appended to every agent's system prompt. The Band platform only delivers messages sent
# via band_send_message(content, mentions) — plain text output is dropped. Open-source
# coder models otherwise loop, so this pins the exact one-pass / one-handoff protocol.
TOOL_DISCIPLINE = """

## How to communicate on Band (REQUIRED — read carefully)
Plain text replies are NOT delivered to the chat. The ONLY way to post anything is to call
the tool `band_send_message(content, mentions)`, and `mentions` MUST contain at least one
handle (the recipient(s) you are handing off to). Your role section above tells you which
handle to use.

## Execution protocol — follow exactly
1. Do your analysis: call each ANALYSIS tool AT MOST ONCE. Never repeat a tool you already
   called. If a tool errors or returns nothing, treat it as "no findings" and move on —
   do NOT retry it.
2. When your analysis is done, make ONE single call to `band_send_message` whose `content`
   is your verdict plus the findings JSON and whose `mentions` is the exact handle named in
   your role section.
3. After that one `band_send_message` call returns successfully, you are DONE. Do not call
   any further tools and do not send any further messages. Stop."""


# Open-source coder models (Qwen3-Coder) tend to keep re-calling tools instead of
# emitting a final hand-off message. A low recursion limit makes the ReAct loop fail
# fast rather than spinning to 50, and the tightened prompts tell the model to call
# each tool at most once and then stop with a single @mention reply.
DEFAULT_RECURSION_LIMIT = 25


def _normalize_mentions(mentions: Any) -> list[str]:
    """Coerce whatever the LLM produced into a list of '@handle' strings.

    Qwen-class open-source models frequently emit the `mentions` array as a *stringified*
    JSON list (e.g. the str '["danny.ssd7/securityagent"]') instead of a real list, which
    fails Band's `mentions: array` schema and sends the agent into an infinite retry loop.
    We accept str | list, parse it, and ensure each handle carries the required '@' prefix.
    """
    if mentions is None:
        return []
    if isinstance(mentions, str):
        s = mentions.strip()
        if s.startswith("[") and s.endswith("]"):
            try:
                mentions = json.loads(s)
            except Exception:
                mentions = [s]
        else:
            mentions = [s]
    out: list[str] = []
    for m in mentions if isinstance(mentions, (list, tuple)) else [mentions]:
        h = str(m).strip().strip("\"'")
        if not h:
            continue
        if not h.startswith("@"):
            h = "@" + h
        out.append(h)
    return out


def _wrap_send_message(platform_tool: Any) -> Any:
    """Return a band_send_message tool with a loosened schema + mention normalization.

    The original tool's args_schema rejects a stringified-list `mentions`, so we expose a
    schema that accepts list OR str, normalize inside, then delegate to the real tool.
    """
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel, Field

    # Per-wrapper idempotency cache. Band's runtime re-runs an agent's pending message on
    # WebSocket reconnect (see `_resync_pending_messages`), and flaky connectivity to
    # app.band.ai (httpx ConnectTimeout/ConnectError) makes those reconnects frequent — so
    # the SAME handoff can be delivered 2–3× (observed in scan/security/risk logs). We dedupe
    # on (content, mentions): a repeat returns the original platform result WITHOUT re-posting,
    # so the chat room shows each verdict exactly once.
    _delivered: dict[tuple[str, tuple[str, ...]], Any] = {}

    class _HandoffArgs(BaseModel):
        content: str = Field(description="The message content to send.")
        mentions: Union[list[str], str] = Field(
            description=(
                "Recipient handle(s) as a JSON array, e.g. "
                '["@danny.ssd7/securityagent"]. At least one required. '
                "Agents: @<username>/<agent-name>. Users: @<username>."
            )
        )

    async def _send(content: str, mentions: Any = None) -> Any:
        norm = _normalize_mentions(mentions)
        import sys

        print(
            f"[band_send_message] mentions_in={mentions!r} -> {norm!r}",
            file=sys.stderr,
            flush=True,
        )
        key = (content, tuple(norm))
        if key in _delivered:
            print(
                "[band_send_message] DEDUP: identical (content, mentions) already "
                "delivered; skipping re-post.",
                file=sys.stderr,
                flush=True,
            )
            return _delivered[key]
        try:
            result = await platform_tool.coroutine(content=content, mentions=norm)
            print(f"[band_send_message] RESULT={result!r}", file=sys.stderr, flush=True)
            _delivered[key] = result
            return result
        except Exception as exc:
            print(
                f"[band_send_message] RAISED {type(exc).__name__}: {exc}",
                file=sys.stderr,
                flush=True,
            )
            raise

    return StructuredTool.from_function(
        coroutine=_send,
        name="band_send_message",
        description=platform_tool.description,
        args_schema=_HandoffArgs,
    )


def build_adapter(
    agent_key: str,
    system_prompt: str,
    tools: Sequence[Any],
    recursion_limit: int = DEFAULT_RECURSION_LIMIT,
) -> Any:
    """Construct the LangGraphAdapter for an agent.

    We use the advanced `graph_factory` pattern (instead of the simple `llm=` pattern) so we
    can intercept Band's injected `band_send_message` tool and wrap it with
    `_wrap_send_message`, fixing the stringified-`mentions` tool-arg bug that otherwise loops
    every agent to the recursion limit. The adapter still renders + injects our system prompt
    because we pass `inject_system_prompt=True` with `custom_section`.
    """
    from band.adapters import LangGraphAdapter
    from langchain.agents import create_agent
    from langgraph.checkpoint.memory import InMemorySaver

    llm = build_llm(agent_key)
    checkpointer = InMemorySaver()
    additional = list(tools)

    def factory(band_tools: list[Any]) -> Any:
        wrapped = [
            _wrap_send_message(t) if getattr(t, "name", "") == "band_send_message" else t
            for t in band_tools
        ]
        return create_agent(model=llm, tools=wrapped + additional, checkpointer=checkpointer)

    return LangGraphAdapter(
        graph_factory=factory,
        custom_section=system_prompt,
        recursion_limit=recursion_limit,
        inject_system_prompt=True,
    )


async def run_agent(
    agent_key: str,
    system_prompt: str,
    tools: Sequence[Any],
    reconnect_retries: int = 0,
    reconnect_backoff: float = 3.0,
) -> None:
    """Create and run a Band agent until cancelled.

    `agent.run()` ends if the Band WebSocket drops (flaky connectivity to app.band.ai —
    httpx ConnectTimeout/ConnectError, observed knocking ReportAgent offline before it could
    post the audit). With `reconnect_retries > 0` we rebuild the agent and resume up to that
    many times, with exponential backoff, so a transient drop doesn't permanently kill the
    agent. A clean return ends the loop; Ctrl-C / cancellation always propagates.
    """
    import sys

    from band import Agent

    agent_id, api_key = resolve_credentials(agent_key)
    attempt = 0
    while True:
        adapter = build_adapter(agent_key, system_prompt, tools)
        agent = Agent.create(adapter=adapter, agent_id=agent_id, api_key=api_key)
        try:
            await agent.run()
            return
        except (KeyboardInterrupt, asyncio.CancelledError):
            raise
        except Exception as exc:
            if attempt >= reconnect_retries:
                raise
            delay = reconnect_backoff * (2**attempt)
            attempt += 1
            print(
                f"[{agent_key}] agent.run() ended with {type(exc).__name__}: {exc} — "
                f"reconnect attempt {attempt}/{reconnect_retries} in {delay:.0f}s",
                file=sys.stderr,
                flush=True,
            )
            await asyncio.sleep(delay)


def main(
    agent_key: str,
    system_prompt: str,
    tools: Sequence[Any],
    reconnect_retries: int = 0,
) -> None:
    """Synchronous entrypoint for `python -m agents.<name>`."""
    from dotenv import load_dotenv

    load_dotenv()
    try:
        asyncio.run(
            run_agent(agent_key, system_prompt, tools, reconnect_retries=reconnect_retries)
        )
    except KeyboardInterrupt:
        pass
