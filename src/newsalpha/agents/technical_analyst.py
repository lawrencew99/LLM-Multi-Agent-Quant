from __future__ import annotations

import json
from typing import Any

from newsalpha.agents.base import call_agent
from newsalpha.core.state import TradingState
from newsalpha.data.connectors.market import get_default_market_connector
from newsalpha.tools.ta import indicators
from newsalpha.utils.logging import get_logger

log = get_logger(__name__)

AGENT_NAME = "technical_analyst"

_market = get_default_market_connector()


def technical_analyst(state: TradingState) -> dict[str, Any]:
    """LangGraph node: compute TA panel, hand it to the LLM, parse signals.

    The deterministic indicator computation lives in `newsalpha.tools.ta.indicators`;
    the LLM only **interprets** the panel — it does not compute anything numerical.
    """
    ticker = state["ticker"]
    as_of = state.get("as_of", "")

    bars = _market.history(ticker, as_of_iso=as_of, lookback_days=90)
    panel = indicators.summarize(bars)

    payload = json.dumps(
        {
            "ticker": ticker,
            "as_of": as_of,
            "indicator_panel": panel,
            "market_snapshot": state.get("market_snapshot"),
        },
        default=str,
    )

    try:
        result = call_agent(AGENT_NAME, user_payload=payload)
    except Exception as exc:  # noqa: BLE001
        log.exception("technical_analyst_failed", ticker=ticker)
        return {
            "technical_report": {
                "error": str(exc),
                "overall_bias": "neutral",
                "overall_strength": 0.0,
                "panel": panel,
            },
            "errors": [f"{AGENT_NAME}: {exc}"],
        }

    report = result.parsed or {
        "overall_bias": "neutral",
        "overall_strength": 0.0,
        "parse_failed": True,
        "raw": result.text[:500],
    }
    report["panel"] = panel  # always echo the deterministic panel for traceability

    return {
        "technical_report": report,
        "cost_usd": result.cost_usd,
    }
