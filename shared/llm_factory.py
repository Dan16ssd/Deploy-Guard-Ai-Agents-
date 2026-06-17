"""Builds a per-agent LangChain chat model from agent_config.yaml + environment.

Both Featherless and AI/ML API expose OpenAI-compatible endpoints, so a single
`ChatOpenAI` pointed at the right base_url/api_key covers every agent. Swapping a
model or provider is a config edit — no code change.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "agent_config.yaml"


@lru_cache(maxsize=1)
def _config() -> dict[str, Any]:
    with _CONFIG_PATH.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val


def agent_names() -> list[str]:
    return list(_config()["agents"].keys())


def resolve_credentials(agent_key: str) -> tuple[str, str]:
    """Return (band_agent_id, band_api_key) for an agent from env."""
    spec = _config()["agents"][agent_key]
    return _require_env(spec["id_env"]), _require_env(spec["key_env"])


def _resolve_api_key(provider: dict[str, Any], agent_key: str) -> str:
    """Pick the provider API key for an agent, spreading agents across a key pool if given.

    The chain makes one LLM call per agent in quick succession; on a small provider tier a
    single key's concurrency/rate budget gets hit (429) and the chain stalls. If several keys
    are available, give each agent a different one so no single key is hit twice per run.

    Precedence (per agent, falls back gracefully):
      1. `<API_KEY_ENV>_<AGENT>`        — explicit per-agent override (e.g. FEATHERLESS_API_KEY_SCAN)
      2. `<API_KEY_ENV>S` (comma list)  — a pool (e.g. FEATHERLESS_API_KEYS=k1,k2,k3) assigned
                                          round-robin by the agent's position in the config
      3. `<API_KEY_ENV>`                — the single shared key (original behavior)
    """
    base_env = provider["api_key_env"]  # e.g. FEATHERLESS_API_KEY

    override = os.environ.get(f"{base_env}_{agent_key.upper()}")
    if override:
        return override

    pool = [
        k.strip() for k in os.environ.get(f"{base_env}S", "").split(",") if k.strip()
    ]
    if pool:
        names = list(_config()["agents"].keys())
        idx = names.index(agent_key) if agent_key in names else 0
        return pool[idx % len(pool)]

    return _require_env(base_env)


def build_llm(agent_key: str) -> Any:
    """Construct the ChatOpenAI client for the given agent.

    Imported lazily so importing this module (e.g. in tests) doesn't require
    langchain_openai to be installed.
    """
    from langchain_openai import ChatOpenAI

    cfg = _config()
    defaults = cfg.get("defaults", {})
    spec = cfg["agents"][agent_key]
    provider_name = spec.get("provider", defaults.get("provider"))
    provider = cfg["providers"][provider_name]

    base_url = _require_env(provider["base_url_env"])
    api_key = _resolve_api_key(provider, agent_key)

    return ChatOpenAI(
        model=spec["model"],
        base_url=base_url,
        api_key=api_key,
        temperature=spec.get("temperature", defaults.get("temperature", 0.1)),
        max_tokens=spec.get("max_tokens", defaults.get("max_tokens", 2048)),
        timeout=spec.get("request_timeout", defaults.get("request_timeout", 120)),
        # The Featherless plan has a small concurrent-unit budget; sequential chain steps can
        # briefly collide (or overlap with backlog) and return 429. Let the OpenAI client ride
        # those out with exponential backoff instead of failing the agent's message.
        max_retries=spec.get("max_retries", defaults.get("max_retries", 6)),
        # Qwen3 hybrid models default to "thinking" mode and emit <think>…</think>
        # in the message body. Agents post to a shared Band room, so disable it for
        # clean verdicts/hand-offs. Non-hybrid (Coder/Instruct) models ignore it.
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
