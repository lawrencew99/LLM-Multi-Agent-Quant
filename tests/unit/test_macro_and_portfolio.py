"""W5 tests for MacroAnalyst + PortfolioManager + W5 graph end-to-end."""

from __future__ import annotations

import pytest

from newsalpha.agents.macro_analyst import _heuristic_regime, macro_analyst
from newsalpha.agents.portfolio_manager import portfolio_manager


@pytest.fixture(autouse=True)
def force_mocks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSALPHA_MOCK_DATA", "1")
    monkeypatch.setenv("NEWSALPHA_MEMORY_BACKEND", "memory")


def test_heuristic_regime_crisis() -> None:
    panel = {"vix": 40, "yield_curve_slope_pct": -0.5, "spy_50dma_vs_200dma": 0.95}
    out = _heuristic_regime(panel)
    assert out["regime"] == "crisis"
    assert out["regime_weight"] <= 0.5


def test_heuristic_regime_bull() -> None:
    panel = {"vix": 15, "yield_curve_slope_pct": 0.5, "spy_50dma_vs_200dma": 1.05}
    out = _heuristic_regime(panel)
    assert out["regime"] == "bull"
    assert out["regime_weight"] >= 0.9


def test_heuristic_regime_bear() -> None:
    panel = {"vix": 25, "yield_curve_slope_pct": -0.3, "spy_50dma_vs_200dma": 0.95}
    out = _heuristic_regime(panel)
    assert out["regime"] == "bear"


def test_heuristic_regime_chop_default() -> None:
    panel = {"vix": 22, "yield_curve_slope_pct": 0.1, "spy_50dma_vs_200dma": 1.0}
    out = _heuristic_regime(panel)
    assert out["regime"] == "chop"


def test_macro_analyst_node_falls_back_on_llm_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from newsalpha.agents import macro_analyst as ma_module

    def boom(*args, **kwargs):
        raise RuntimeError("API down")

    monkeypatch.setattr(ma_module, "call_agent", boom)

    result = ma_module.macro_analyst({"ticker": "AAPL", "as_of": "2023-06-01T00:00:00Z"})
    assert "macro_context" in result
    assert "macro_report" in result
    assert "regime" in result["macro_report"]
    assert "errors" in result


def test_portfolio_manager_no_orders_no_op() -> None:
    state = {"final_orders": [], "ticker": "AAPL"}
    out = portfolio_manager(state)
    assert out == {}


def test_portfolio_manager_resizes_with_regime_weight() -> None:
    state = {
        "ticker": "AAPL",
        "final_orders": [{
            "ticker": "AAPL",
            "side": "long",
            "size_pct": 0.04,
            "stop_loss_price": 145,
            "take_profit_price": 165,
            "entry_price_hint": 150,
            "thesis": "test",
        }],
        "macro_report": {"regime": "bear", "regime_weight": 0.5},
        "judge_verdict": {"conviction": 0.8, "directional_bias": "long"},
    }
    out = portfolio_manager(state)
    assert "final_orders" in out
    assert out["final_orders"][0]["size_pct"] < 0.04  # downscaled
    assert "portfolio_decision" in out
    assert out["portfolio_decision"]["regime"] == "bear"


def test_portfolio_manager_respects_max_single_cap() -> None:
    state = {
        "ticker": "AAPL",
        "final_orders": [{
            "ticker": "AAPL", "side": "long",
            "size_pct": 0.20,  # well over max
            "stop_loss_price": 145, "take_profit_price": 165,
            "entry_price_hint": 150, "thesis": "test",
        }],
        "macro_report": {"regime": "bull", "regime_weight": 1.0},
        "judge_verdict": {"conviction": 1.0},
    }
    out = portfolio_manager(state)
    assert out["final_orders"][0]["size_pct"] <= 0.05


def test_portfolio_manager_audit_trail_present() -> None:
    state = {
        "ticker": "AAPL",
        "final_orders": [{
            "ticker": "AAPL", "side": "long", "size_pct": 0.03,
            "stop_loss_price": 145, "take_profit_price": 165,
            "entry_price_hint": 150, "thesis": "test",
        }],
        "macro_report": {"regime": "bull", "regime_weight": 1.0},
        "judge_verdict": {"conviction": 0.75},
    }
    out = portfolio_manager(state)
    audit = out["portfolio_decision"]["audit"]
    assert len(audit) == 1
    assert "sizing_breakdown" in audit[0]
    assert "regime_weight" in audit[0]
