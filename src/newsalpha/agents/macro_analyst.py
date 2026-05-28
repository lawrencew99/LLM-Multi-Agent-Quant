"""MacroAnalyst — produces a macro regime label and weighting context.

Reads FRED data (or mock) for VIX / yield curve / Fed funds rate, hands the
panel to an LLM for narrative interpretation, then publishes:
  - regime: bull | bear | chop | crisis
  - regime_weight: 0..1 (used downstream to scale position sizing)
  - rationale: text for debate context

In W5 this runs once per graph invocation (cheap — cached for 1h in
production). MacroContext writes to state.macro_context.
"""

from __future__ import annotations

import json
from typing import Any

from newsalpha.agents.base import call_agent
from newsalpha.core.state import TradingState
from newsalpha.utils.logging import get_logger

log = get_logger(__name__)

AGENT_NAME = "macro_analyst"


def _mock_macro_panel() -> dict[str, Any]:
    """Deterministic mock macro data — used when FRED is unavailable."""
    return {
        "vix": 18.5,
        "ten_year_yield_pct": 4.3,
        "two_year_yield_pct": 4.7,
        "yield_curve_slope_pct": -0.4,
        "fed_funds_rate_pct": 5.25,
        "spy_50dma_vs_200dma": 1.02,
        "spy_30d_return_pct": 1.8,
    }


def _fetch_macro_panel() -> dict[str, Any]:
    """Try FRED; fall back to mock.

    Real FRED integration: would call `fred.get_series('VIXCLS')` etc.
    For W5 MVP, return deterministic mock — keeps test surface narrow.
    """
    import os
    if os.environ.get("NEWSALPHA_MOCK_DATA") == "1":
        return _mock_macro_panel()
    return _mock_macro_panel()


def macro_analyst(state: TradingState) -> dict[str, Any]:
    """LangGraph node: assess macro regime and emit regime_weight."""
    panel = _fetch_macro_panel()

    payload = json.dumps(
        {
            "ticker": state.get("ticker", ""),
            "as_of": state.get("as_of", ""),
            "macro_panel": panel,
        },
        default=str,
    )

    try:
        result = call_agent(AGENT_NAME, user_payload=payload)
    except Exception as exc:  # noqa: BLE001
        log.exception("macro_analyst_failed")
        report = _heuristic_regime(panel)
        report["error"] = str(exc)
        return {
            "macro_context": panel,
            "macro_report": report,
            "errors": [f"{AGENT_NAME}: {exc}"],
        }

    report = result.parsed or _heuristic_regime(panel)
    report["panel"] = panel

    return {
        "macro_context": panel,
        "macro_report": report,
        "cost_usd": result.cost_usd,
    }


def _heuristic_regime(panel: dict[str, Any]) -> dict[str, Any]:
    """Deterministic regime classification — fallback when LLM is unavailable.

    Maps VIX + 200dma + curve to one of 4 regimes with rule-of-thumb weights.
    """
    vix = float(panel.get("vix", 20))
    curve = float(panel.get("yield_curve_slope_pct", 0))
    spy_trend = float(panel.get("spy_50dma_vs_200dma", 1.0))

    if vix > 35:
        regime = "crisis"
        weight = 0.3
    elif spy_trend > 1.02 and vix < 20:
        regime = "bull"
        weight = 1.0
    elif spy_trend < 0.98 and curve < 0:
        regime = "bear"
        weight = 0.5
    else:
        regime = "chop"
        weight = 0.7

    return {
        "regime": regime,
        "regime_weight": weight,
        "rationale": f"Heuristic: VIX={vix} curve={curve:+.2f} trend={spy_trend:.2f}",
    }
