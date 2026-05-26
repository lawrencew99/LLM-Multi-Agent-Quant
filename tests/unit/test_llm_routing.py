from __future__ import annotations

from newsalpha.llm.routing import (
    MODEL_IDS,
    PRICING,
    estimate_cost,
    load_agent_configs,
)


def test_every_aliased_model_has_pricing() -> None:
    for alias, model_id in MODEL_IDS.items():
        assert model_id in PRICING, f"missing pricing for alias {alias}"


def test_estimate_cost_sums_components() -> None:
    cost = estimate_cost(
        "claude-sonnet-4-6",
        input_tokens=1_000_000,
        output_tokens=0,
    )
    assert cost == PRICING["claude-sonnet-4-6"]["in"]


def test_agent_configs_resolve_known_aliases() -> None:
    cfgs = load_agent_configs()
    assert "news_collector" in cfgs
    assert "trader" in cfgs
    for cfg in cfgs.values():
        assert cfg.model_id in PRICING
