from __future__ import annotations

import json
from typing import Any

from newsalpha.agents.base import call_agent
from newsalpha.core.state import TradingState
from newsalpha.utils.logging import get_logger

log = get_logger(__name__)

AGENT_NAME = "fundamental_analyst"

_NEUTRAL = {
    "scores": {
        "growth": 5.0,
        "margin": 5.0,
        "cash": 5.0,
        "leverage": 5.0,
        "valuation": 5.0,
    },
    "event_driven": False,
    "rationale": "fallback neutral",
    "citations": [],
}


def fundamental_analyst(state: TradingState) -> dict[str, Any]:
    """LangGraph node: emit a 5-dim fundamentals delta from news.

    Without a real financials feed (planned for Finnhub `/stock/financials-reported`
    in W3+), the agent currently reasons from news content alone. The prompt
    explicitly tells it to leave dimensions at the 5.0 baseline when uninformed.
    """
    payload = json.dumps(
        {
            "ticker": state["ticker"],
            "as_of": state.get("as_of", ""),
            "news_items": state.get("news_items", []),
            "market_snapshot": state.get("market_snapshot"),
            # TODO(W3): inject finnhub /stock/financials-reported snapshot here
        },
        default=str,
    )

    try:
        result = call_agent(AGENT_NAME, user_payload=payload)
    except Exception as exc:  # noqa: BLE001
        log.exception("fundamental_analyst_failed", ticker=state["ticker"])
        return {
            "fundamental_report": {**_NEUTRAL, "error": str(exc)},
            "errors": [f"{AGENT_NAME}: {exc}"],
        }

    report = result.parsed or {**_NEUTRAL, "parse_failed": True, "raw": result.text[:500]}
    return {
        "fundamental_report": report,
        "cost_usd": result.cost_usd,
    }
