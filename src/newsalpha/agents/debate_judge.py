from __future__ import annotations

import json
from typing import Any

from newsalpha.agents.base import call_agent
from newsalpha.core.state import TradingState
from newsalpha.utils.logging import get_logger

log = get_logger(__name__)

AGENT_NAME = "debate_judge"


def debate_judge(state: TradingState) -> dict[str, Any]:
    """LangGraph node: score the Bull/Bear debate, emit a calibrated verdict.

    `judge_verdict.conviction` is the gate the Trader checks (default threshold
    is `debate.min_conviction_to_trade` in agents.yaml, 0.6).
    """
    payload = json.dumps(
        {
            "ticker": state["ticker"],
            "as_of": state.get("as_of", ""),
            "debate_mode": state.get("debate_mode", "adversarial"),
            "rounds_completed": state.get("debate_round", 1),
            "analyst_reports": {
                "sentiment": state.get("sentiment_report"),
                "fundamental": state.get("fundamental_report"),
                "technical": state.get("technical_report"),
            },
            "bull_arguments": state.get("bull_arguments", []),
            "bear_arguments": state.get("bear_arguments", []),
            "market_snapshot": state.get("market_snapshot"),
        },
        default=str,
    )

    try:
        result = call_agent(AGENT_NAME, user_payload=payload)
    except Exception as exc:  # noqa: BLE001
        log.exception("debate_judge_failed", ticker=state["ticker"])
        return {
            "judge_verdict": {
                "error": str(exc),
                "winner": "neutral",
                "directional_bias": "neutral",
                "conviction": 0.0,
            },
            "errors": [f"{AGENT_NAME}: {exc}"],
        }

    verdict = result.parsed or {
        "winner": "neutral",
        "directional_bias": "neutral",
        "conviction": 0.0,
        "parse_failed": True,
        "raw": result.text[:500],
    }
    return {
        "judge_verdict": verdict,
        "cost_usd": result.cost_usd,
    }
