from __future__ import annotations

import json
from typing import Any

from newsalpha.agents.base import call_agent
from newsalpha.core.state import TradingState
from newsalpha.utils.logging import get_logger

log = get_logger(__name__)

AGENT_NAME = "sentiment_analyst"


def sentiment_analyst(state: TradingState) -> dict[str, Any]:
    """LangGraph node: read news_items + market_snapshot, emit sentiment_report."""
    payload = json.dumps(
        {
            "ticker": state["ticker"],
            "as_of": state.get("as_of", ""),
            "news_items": state.get("news_items", []),
            "market_snapshot": state.get("market_snapshot"),
        },
        default=str,
    )

    try:
        result = call_agent(AGENT_NAME, user_payload=payload)
    except Exception as exc:  # noqa: BLE001
        log.exception("sentiment_analyst_failed", ticker=state["ticker"])
        return {
            "sentiment_report": {"error": str(exc), "polarity": 0.0, "confidence": 0.0},
            "errors": [f"{AGENT_NAME}: {exc}"],
        }

    report = result.parsed or {
        "polarity": 0.0,
        "confidence": 0.0,
        "rationale": result.text[:500],
        "parse_failed": True,
    }
    return {
        "sentiment_report": report,
        "cost_usd": result.cost_usd,
    }
