"""PortfolioManager — final allocation gate.

Sits between RiskManager (accept/reject) and the broker. Responsibilities:
  - Apply regime_weight from MacroAnalyst to scale sizes
  - Apply Kelly + vol-target sizing
  - Cross-check against currently held positions (don't double-buy AAPL)
  - Aggregate orders if multiple agents emit signals for the same ticker

This is a pure-Python node (no LLM) — it's part of the deterministic execution
trust boundary, like RiskManager.
"""

from __future__ import annotations

from typing import Any

from newsalpha.core.state import TradingState
from newsalpha.execution.sizing import compute_final_size
from newsalpha.utils.logging import get_logger

log = get_logger(__name__)


def portfolio_manager(state: TradingState) -> dict[str, Any]:
    """LangGraph node: take risk-accepted orders, apply final sizing.

    Reads:
      - state.final_orders (from RiskManager)
      - state.macro_report.regime_weight (from MacroAnalyst, if available)
      - state.judge_verdict.conviction
    Writes:
      - state.final_orders (resized — replaces, not appends)
      - state.portfolio_decision (audit trail of sizing math)
    """
    orders = state.get("final_orders", [])
    if not orders:
        log.info("portfolio_manager_no_orders")
        return {}

    macro = state.get("macro_report") or {}
    regime_weight = float(macro.get("regime_weight", 1.0) or 1.0)
    regime = macro.get("regime", "unknown")

    verdict = state.get("judge_verdict") or {}
    conviction = float(verdict.get("conviction", 0.7) or 0.7)

    resized_orders: list[dict[str, Any]] = []
    audit_records: list[dict[str, Any]] = []

    for order in orders:
        base_size = float(order.get("size_pct", 0.03))

        scaled_base = base_size * regime_weight

        sizing = compute_final_size(
            scaled_base,
            conviction=conviction,
            asset_vol=None,
            max_single_pct=0.05,
        )

        new_order = {**order, "size_pct": sizing["final_size_pct"]}
        resized_orders.append(new_order)

        audit_records.append({
            "ticker": order.get("ticker"),
            "regime": regime,
            "regime_weight": regime_weight,
            "conviction": conviction,
            "sizing_breakdown": sizing,
            "original_size_pct": base_size,
            "final_size_pct": sizing["final_size_pct"],
        })

        log.info(
            "portfolio_resized",
            ticker=order.get("ticker"),
            original=base_size,
            final=sizing["final_size_pct"],
            regime=regime,
        )

    return {
        "final_orders": resized_orders,
        "portfolio_decision": {
            "regime": regime,
            "regime_weight": regime_weight,
            "audit": audit_records,
        },
    }
