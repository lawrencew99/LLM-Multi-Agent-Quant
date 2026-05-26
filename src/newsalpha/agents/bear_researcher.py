from __future__ import annotations

import json
from typing import Any

from newsalpha.agents.base import call_agent
from newsalpha.core.config import load_yaml_config
from newsalpha.core.state import TradingState
from newsalpha.utils.logging import get_logger

log = get_logger(__name__)

AGENT_NAME = "bear_researcher"


def _load_debate_cfg() -> dict[str, Any]:
    return load_yaml_config("agents").get("debate", {})


def bear_researcher(state: TradingState) -> dict[str, Any]:
    """LangGraph node: build the strongest bear thesis from analyst reports."""
    debate_cfg = _load_debate_cfg()
    round_num = state.get("debate_round", 1)

    payload = json.dumps(
        {
            "ticker": state["ticker"],
            "as_of": state.get("as_of", ""),
            "debate_mode": state.get("debate_mode", debate_cfg.get("mode", "adversarial")),
            "round": round_num,
            "max_rounds": debate_cfg.get("rounds", 2),
            "analyst_reports": {
                "sentiment": state.get("sentiment_report"),
                "fundamental": state.get("fundamental_report"),
                "technical": state.get("technical_report"),
            },
            "news_items": state.get("news_items", []),
            "market_snapshot": state.get("market_snapshot"),
            "prior_bull_arguments": state.get("bull_arguments", []),
            "prior_bear_arguments": state.get("bear_arguments", []),
            "judge_question": (state.get("judge_verdict") or {}).get("next_round_question"),
        },
        default=str,
    )

    try:
        result = call_agent(AGENT_NAME, user_payload=payload)
    except Exception as exc:  # noqa: BLE001
        log.exception("bear_researcher_failed", ticker=state["ticker"])
        return {
            "bear_arguments": [{"error": str(exc), "round": round_num, "stance": "bear", "conviction": 0.0}],
            "errors": [f"{AGENT_NAME}: {exc}"],
        }

    argument = result.parsed or {
        "round": round_num,
        "stance": "bear",
        "thesis_summary": "parse_failed",
        "claims": [],
        "conviction": 0.0,
        "parse_failed": True,
        "raw": result.text[:500],
    }
    return {
        "bear_arguments": [argument],
        "cost_usd": result.cost_usd,
    }
