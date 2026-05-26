from __future__ import annotations

from functools import lru_cache
from typing import Any

from newsalpha.core.config import REPO_ROOT
from newsalpha.llm.client import LLMCallResult, get_llm_client
from newsalpha.llm.routing import AgentLLMConfig, load_agent_configs
from newsalpha.utils.logging import get_logger

log = get_logger(__name__)

PROMPTS_DIR = REPO_ROOT / "configs" / "prompts" / "system"


@lru_cache(maxsize=32)
def load_system_prompt(agent_name: str) -> str:
    """Read configs/prompts/system/{agent_name}.md once per process."""
    path = PROMPTS_DIR / f"{agent_name}.md"
    if not path.exists():
        raise FileNotFoundError(f"System prompt not found: {path}")
    return path.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _agent_configs() -> dict[str, AgentLLMConfig]:
    return load_agent_configs()


def get_agent_config(agent_name: str) -> AgentLLMConfig:
    cfgs = _agent_configs()
    if agent_name not in cfgs:
        raise KeyError(f"No agents.yaml entry for '{agent_name}'")
    return cfgs[agent_name]


def call_agent(
    agent_name: str,
    *,
    user_payload: str,
    extra_system: str | None = None,
) -> LLMCallResult:
    """Run one agent: load system prompt, build user message, call LLM, return result.

    The LLM's text output is JSON-parsed (best-effort) — `LLMCallResult.parsed` is
    `None` on failure. Use `call_agent(...).parsed or {}` to soak up bad outputs.
    """
    cfg = get_agent_config(agent_name)
    system = load_system_prompt(agent_name)
    if extra_system:
        system = f"{system}\n\n---\n\n{extra_system}"

    return get_llm_client().call(
        cfg,
        system=system,
        messages=[{"role": "user", "content": user_payload}],
        expect_json=True,
    )
