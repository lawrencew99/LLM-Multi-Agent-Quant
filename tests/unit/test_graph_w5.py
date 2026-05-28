"""W5 graph integration test — exercises the full 12-agent pipeline."""

from __future__ import annotations

from typing import Any

import pytest

from newsalpha.core.graph import build_graph


def _stub_llm_result(**parsed_overrides: Any):
    """Build a fake LLMCallResult that returns deterministic JSON."""
    from newsalpha.llm.client import LLMCallResult

    parsed = {
        "polarity": 0.6,
        "confidence": 0.7,
        "rationale": "stub",
        "scores": {"growth": 7, "profit": 6, "cash": 7, "leverage": 6, "valuation": 6},
        "overall_bias": "long",
        "overall_strength": 0.7,
        "regime": "bull",
        "regime_weight": 1.0,
        "claims": [{"id": "c1", "text": "earnings beat", "evidence_id": "n1"}],
        "conviction": 0.75,
        "rebuts_bull_id": "c1",
        "winner": "bull",
        "directional_bias": "long",
        "rubric_scores": {"evidence": 8, "logic": 8, "completeness": 7, "novelty": 7, "risk": 7},
        "rationale_text": "bullish",
        "action": "buy",
        "ticker": "AAPL",
        "side": "long",
        "suggested_size_pct": 0.04,
        "entry_price_hint": 150.0,
        "stop_loss_price": 145.0,
        "take_profit_price": 165.0,
        "thesis_one_liner": "stub thesis",
        "decisive_signals": [],
        "risks": [],
        "expected_holding_days": 7,
    }
    parsed.update(parsed_overrides)

    class _Msg:
        usage = type("U", (), {
            "input_tokens": 100, "output_tokens": 50,
            "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
        })()

    return LLMCallResult(
        text="{}",
        parsed=parsed,
        raw_message=_Msg(),
        cost_usd=0.001,
        latency_ms=100,
        cache_read_tokens=0,
        cache_write_tokens=0,
    )


@pytest.fixture(autouse=True)
def setup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSALPHA_MOCK_DATA", "1")
    monkeypatch.setenv("NEWSALPHA_MEMORY_BACKEND", "memory")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    from newsalpha.data.connectors import market as market_mod
    from newsalpha.data.connectors import news as news_mod
    monkeypatch.setattr(market_mod, "get_default_market_connector",
                        market_mod.MockMarketDataConnector)
    monkeypatch.setattr(news_mod, "get_default_news_connector",
                        news_mod.MockNewsConnector)

    from newsalpha.agents import news_collector as nc_mod
    monkeypatch.setattr(nc_mod, "_market", market_mod.MockMarketDataConnector())
    monkeypatch.setattr(nc_mod, "_news", news_mod.MockNewsConnector())

    from newsalpha.agents import technical_analyst as ta_mod
    monkeypatch.setattr(ta_mod, "_market", market_mod.MockMarketDataConnector())

    from newsalpha.agents import (
        base as base_mod,
        bear_researcher,
        bull_researcher,
        debate_judge,
        fundamental_analyst,
        macro_analyst,
        sentiment_analyst,
        technical_analyst,
        trader,
    )

    def _fake(*a, **kw):
        return _stub_llm_result()

    for mod in (
        base_mod, bear_researcher, bull_researcher, debate_judge,
        fundamental_analyst, macro_analyst, sentiment_analyst,
        technical_analyst, trader,
    ):
        if hasattr(mod, "call_agent"):
            monkeypatch.setattr(mod, "call_agent", _fake)


def test_w5_graph_runs_end_to_end_high_conviction() -> None:
    graph = build_graph()
    initial = {
        "trigger": {"type": "test"},
        "ticker": "AAPL",
        "as_of": "2023-06-01T00:00:00Z",
        "trace_id": "test-w5",
        "debate_round": 0,
        "debate_mode": "adversarial",
        "cost_usd": 0.0,
        "latency_ms": 0,
        "bull_arguments": [],
        "bear_arguments": [],
        "final_orders": [],
        "errors": [],
    }
    final_state = graph.invoke(initial)

    assert final_state.get("ticker") == "AAPL"
    assert final_state.get("macro_report") is not None
    assert final_state.get("macro_report", {}).get("regime") in ("bull", "bear", "chop", "crisis")
    assert final_state.get("trade_signal") is not None
    assert final_state.get("risk_decision") is not None
    if final_state["risk_decision"].get("accepted"):
        assert final_state.get("portfolio_decision") is not None
        assert "audit" in final_state["portfolio_decision"]


def test_w5_graph_macro_report_has_panel() -> None:
    graph = build_graph()
    initial = {
        "trigger": {"type": "test"},
        "ticker": "AAPL",
        "as_of": "2023-06-01T00:00:00Z",
        "trace_id": "test-w5",
        "debate_round": 0,
        "debate_mode": "adversarial",
        "cost_usd": 0.0,
        "latency_ms": 0,
        "bull_arguments": [],
        "bear_arguments": [],
        "final_orders": [],
        "errors": [],
    }
    final_state = graph.invoke(initial)
    assert "panel" in (final_state.get("macro_report") or {})
    assert "vix" in (final_state.get("macro_context") or {})
