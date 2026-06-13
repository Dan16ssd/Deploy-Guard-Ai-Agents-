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
    api_key = _require_env(provider["api_key_env"])

    return ChatOpenAI(
        model=spec["model"],
        base_url=base_url,
        api_key=api_key,
        temperature=spec.get("temperature", defaults.get("temperature", 0.1)),
        max_tokens=spec.get("max_tokens", defaults.get("max_tokens", 2048)),
        timeout=spec.get("request_timeout", defaults.get("request_timeout", 120)),
    )
