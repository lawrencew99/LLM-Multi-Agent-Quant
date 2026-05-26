from __future__ import annotations

import json
from typing import Any

from newsalpha.agents.base import call_agent
from newsalpha.core.state import TradingState
from newsalpha.utils.logging import get_logger

log = get_logger(__name__)

AGENT_NAME = "trader"


def _hold_signal(ticker: str, reason: str) -> dict[str, Any]:
    return {
        "action": "hold",
        "ticker": ticker,
        "side": "flat",
        "conviction": 0.0,
        "suggested_size_pct": 0.0,
        "entry_price_hint": 0.0,
        "stop_loss_price": 0.0,
        "take_profit_price": 0.0,
        "thesis_one_liner": reason,
        "decisive_signals": [],
        "risks": [],
        "expected_holding_days": 0,
    }


def trader(state: TradingState) -> dict[str, Any]:
    """LangGraph node: produce the executable trade signal (or `hold`).

    Honors the conviction gate — when `judge_verdict.conviction` is below
    threshold OR the bias is `neutral`, we short-circuit to a `hold` signal
    *without* spending an LLM call. This keeps cost predictable and matches
    the system's risk posture (never trade on weak signal).
    """
    ticker = state["ticker"]
    verdict = state.get("judge_verdict") or {}
    bias = verdict.get("directional_bias", "neutral")
    conv = float(verdict.get("conviction", 0.0) or 0.0)

    if bias == "neutral" or conv < 0.6:
        return {
            "trade_signal": _hold_signal(
                ticker, f"hold: bias={bias} conviction={conv:.2f} below threshold"
            ),
        }

    payload = json.dumps(
        {
            "ticker": ticker,
            "as_of": state.get("as_of", ""),
            "judge_verdict": verdict,
            "analyst_reports": {
                "sentiment": state.get("sentiment_report"),
                "fundamental": state.get("fundamental_report"),
                "technical": state.get("technical_report"),
            },
            "market_snapshot": state.get("market_snapshot"),
            # W3 placeholder — portfolio context wired in W5 with PortfolioManager.
            "portfolio_context": {
                "current_position_pct": 0.0,
                "available_buying_power_usd": 100_000,
                "open_position_count": 0,
            },
        },
        default=str,
    )

    try:
        result = call_agent(AGENT_NAME, user_payload=payload)
    except Exception as exc:  # noqa: BLE001
        log.exception("trader_failed", ticker=ticker)
        return {
            "trade_signal": _hold_signal(ticker, f"hold: trader error {exc}"),
            "errors": [f"{AGENT_NAME}: {exc}"],
        }

    signal = result.parsed or _hold_signal(ticker, "hold: trader parse_failed")
    signal.setdefault("ticker", ticker)
    return {
        "trade_signal": signal,
        "cost_usd": result.cost_usd,
    }
