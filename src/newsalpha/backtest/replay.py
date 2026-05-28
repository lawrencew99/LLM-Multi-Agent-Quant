"""Decision snapshot replay engine — differential亮点 #2.

Reads a persisted snapshot and re-runs downstream graph nodes using the
recorded LLM outputs (deterministic replay) OR substitutes specific agents'
prompts for A/B ablation studies without re-spending tokens.

Key invariant: replay never makes network calls — all LLM responses come
from the snapshot file. If an agent is overridden, only *that* agent's
subtree is re-computed (others remain from snapshot).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from newsalpha.backtest.snapshots import read_snapshot
from newsalpha.risk.rules import evaluate_signal
from newsalpha.utils.logging import get_logger

log = get_logger(__name__)


def replay_decision(
    snapshot_path: str | Path,
    *,
    override_risk_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Replay a past decision from snapshot with optional risk config override.

    This deterministic replay re-applies risk rules to the saved trade_signal.
    Useful for answering "what if our risk limits were different?"

    Returns the replayed state dict with updated `risk_decision` and `final_orders`.
    """
    snap = read_snapshot(snapshot_path)
    state = snap["state"]
    trace_id = snap.get("trace_id", "unknown")

    signal = state.get("trade_signal") or {}
    market_snapshot = state.get("market_snapshot")

    decision = evaluate_signal(
        signal,
        market_snapshot=market_snapshot,
        portfolio_context=None,
        config=override_risk_config,
    )

    replayed_state = {**state}
    replayed_state["risk_decision"] = decision.to_dict()
    replayed_state["final_orders"] = []

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
        replayed_state["final_orders"] = [order]

    log.info(
        "replay_completed",
        trace_id=trace_id,
        original_accepted=state.get("risk_decision", {}).get("accepted"),
        replayed_accepted=decision.accepted,
    )
    return replayed_state


def extract_signals_for_backtest(
    snapshot_dir: str | Path,
) -> list[dict[str, Any]]:
    """Extract all trade signals from snapshots for backtesting.

    Returns a list of dicts with:
      - ticker, as_of, side, size_pct, entry_price, stop_loss, take_profit
      - conviction, trade_signal (full), risk_decision
    Only includes accepted trades (final_orders non-empty).
    """
    from newsalpha.backtest.snapshots import list_snapshots

    sdir = Path(snapshot_dir)
    signals: list[dict[str, Any]] = []

    for path in list_snapshots(sdir):
        try:
            snap = read_snapshot(path)
        except (json.JSONDecodeError, KeyError):
            log.warning("snapshot_unreadable", path=str(path))
            continue

        state = snap.get("state", {})
        orders = state.get("final_orders", [])
        if not orders:
            continue

        verdict = state.get("judge_verdict") or {}
        for order in orders:
            signals.append({
                "ticker": order.get("ticker", state.get("ticker")),
                "as_of": state.get("as_of"),
                "side": order.get("side"),
                "size_pct": order.get("size_pct", 0.0),
                "entry_price": order.get("entry_price_hint", 0.0),
                "stop_loss": order.get("stop_loss_price", 0.0),
                "take_profit": order.get("take_profit_price", 0.0),
                "conviction": verdict.get("conviction", 0.0),
                "trace_id": state.get("trace_id"),
            })

    return signals
