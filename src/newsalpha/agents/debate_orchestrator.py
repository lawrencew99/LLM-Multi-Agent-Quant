from __future__ import annotations

from typing import Any

from newsalpha.core.config import load_yaml_config
from newsalpha.core.state import TradingState
from newsalpha.utils.logging import get_logger

log = get_logger(__name__)


def debate_orchestrator(state: TradingState) -> dict[str, Any]:
    """Seed debate state from config before round 1, no-op after.

    Pure-Python control node — does not call any LLM. Reads `debate.mode` and
    `debate.rounds` from `configs/agents.yaml` at request time so an A/B switch
    only requires a config edit + replay.
    """
    if "debate_round" in state and state.get("debate_mode"):
        return {}

    cfg = load_yaml_config("agents").get("debate", {})
    return {
        "debate_round": 1,
        "debate_mode": cfg.get("mode", "adversarial"),
    }


def debate_round_advancer(state: TradingState) -> dict[str, Any]:
    """Increment the debate round after each bull+bear pair."""
    current = state.get("debate_round", 1)
    return {"debate_round": current + 1}


def should_continue_debate(state: TradingState) -> str:
    """Routing edge: more rounds, or send to judge?

    `debate_round` here reflects the *next* round to run (the advancer just
    incremented it after bull+bear completed). With `rounds: 2`, we run rounds
    1 and 2; after round 2 the advancer sets round=3 → 3 > 2 → judge.
    """
    cfg = load_yaml_config("agents").get("debate", {})
    max_rounds = int(cfg.get("rounds", 2))
    next_round = state.get("debate_round", 1)
    if next_round <= max_rounds:
        return "continue"
    return "judge"


def should_trade(state: TradingState) -> str:
    """Routing edge after the judge: trade or stop here.

    Returns "trade" only when the judge declares a non-neutral bias AND meets
    the conviction threshold from `configs/agents.yaml`.
    """
    cfg = load_yaml_config("agents").get("debate", {})
    threshold = float(cfg.get("min_conviction_to_trade", 0.6))

    verdict = state.get("judge_verdict") or {}
    bias = verdict.get("directional_bias", "neutral")
    conv = float(verdict.get("conviction", 0.0) or 0.0)

    if bias != "neutral" and conv >= threshold:
        return "trade"
    return "stop"


def log_only(state: TradingState) -> dict[str, Any]:
    """Terminal node when we decide not to trade. Pure logging — no state mutation."""
    verdict = state.get("judge_verdict") or {}
    log.info(
        "log_only_no_trade",
        ticker=state.get("ticker"),
        conviction=verdict.get("conviction"),
        bias=verdict.get("directional_bias"),
        winner=verdict.get("winner"),
    )
    return {}
