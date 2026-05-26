from __future__ import annotations

from typing import Any

from newsalpha.core.state import TradingState
from newsalpha.risk.rules import evaluate_signal
from newsalpha.utils.logging import get_logger

log = get_logger(__name__)


def risk_manager(state: TradingState) -> dict[str, Any]:
    """LangGraph node: deterministic risk evaluation.

    Wraps `risk.rules.evaluate_signal` so the graph stays declarative. No LLM
    calls — this is the trust boundary between LLM judgment and real money.
    """
    signal = state.get("trade_signal") or {}
    decision = evaluate_signal(
        signal,
        market_snapshot=state.get("market_snapshot"),
        portfolio_context=None,
    )

    log.info(
        "risk_decision",
        ticker=state.get("ticker"),
        accepted=decision.accepted,
        final_size_pct=decision.final_size_pct,
        reasons=decision.reasons,
    )

    out: dict[str, Any] = {"risk_decision": decision.to_dict()}

    if decision.accepted:
        order = {
            "ticker": signal.get("ticker", state.get("ticker")),
            "side": signal["side"],
            "size_pct": decision.final_size_pct,
            "stop_loss_price": decision.final_stop_price,
            "take_profit_price": float(signal.get("take_profit_price") or 0.0),
            "entry_price_hint": float(signal.get("entry_price_hint") or 0.0),
            "thesis": signal.get("thesis_one_liner", ""),
        }
        out["final_orders"] = [order]

    return out
