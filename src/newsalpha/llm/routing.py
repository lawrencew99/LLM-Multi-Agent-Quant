from __future__ import annotations

from dataclasses import dataclass

from newsalpha.core.config import load_yaml_config

# Concrete model IDs — kept in one place so the agents.yaml can use short aliases.
MODEL_IDS: dict[str, str] = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-7",
}

# Per-million-token USD pricing (input / output / cache_write / cache_read).
# Update these from Anthropic's pricing page when models or rates change.
PRICING: dict[str, dict[str, float]] = {
    "claude-haiku-4-5-20251001": {"in": 1.0, "out": 5.0, "cw": 1.25, "cr": 0.10},
    "claude-sonnet-4-6": {"in": 3.0, "out": 15.0, "cw": 3.75, "cr": 0.30},
    "claude-opus-4-7": {"in": 15.0, "out": 75.0, "cw": 18.75, "cr": 1.50},
}


@dataclass(frozen=True)
class AgentLLMConfig:
    """Resolved per-agent LLM configuration."""

    agent: str
    model_alias: str
    model_id: str
    temperature: float
    max_tokens: int
    cache_system_prompt: bool
    effort: str | None = None  # low | medium | high | xhigh | max — Opus only


# Models that reject `temperature` / `top_p` / `top_k` (Opus 4.7+).
# Source: shared/model-migration.md → Migrating to Opus 4.7.
NO_SAMPLING_PARAMS: frozenset[str] = frozenset({"claude-opus-4-7"})


def supports_temperature(model_id: str) -> bool:
    return model_id not in NO_SAMPLING_PARAMS


def load_agent_configs() -> dict[str, AgentLLMConfig]:
    """Read configs/agents.yaml and resolve every agent's model id."""
    cfg = load_yaml_config("agents")
    out: dict[str, AgentLLMConfig] = {}
    for name, spec in cfg["agents"].items():
        alias = spec["model"]
        if alias not in MODEL_IDS:
            raise ValueError(f"Unknown model alias '{alias}' for agent '{name}'")
        out[name] = AgentLLMConfig(
            agent=name,
            model_alias=alias,
            model_id=MODEL_IDS[alias],
            temperature=float(spec.get("temperature", 0.2)),
            max_tokens=int(spec.get("max_tokens", 2048)),
            cache_system_prompt=bool(spec.get("cache_system_prompt", True)),
            effort=spec.get("effort"),
        )
    return out


def estimate_cost(
    model_id: str,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_write_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """Estimate USD cost for a single LLM call given token counts."""
    rates = PRICING.get(model_id)
    if rates is None:
        return 0.0
    return (
        input_tokens * rates["in"]
        + output_tokens * rates["out"]
        + cache_write_tokens * rates["cw"]
        + cache_read_tokens * rates["cr"]
    ) / 1_000_000
