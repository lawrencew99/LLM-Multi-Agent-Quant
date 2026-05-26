"""End-to-end W3 graph test: news → analysts → debate (2 rounds) → judge → trader → risk."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from newsalpha.agents import (
    bear_researcher,
    bull_researcher,
    debate_judge,
    fundamental_analyst,
    sentiment_analyst,
    technical_analyst,
    trader,
)
from newsalpha.core.graph import build_graph
from newsalpha.core.state import TradingState
from newsalpha.llm.client import LLMCallResult


def _fake(parsed: dict[str, Any]):
    def _stub(*a: Any, **k: Any) -> LLMCallResult:
        return LLMCallResult(
            text="{}",
            parsed=parsed,
            raw_message=None,  # type: ignore[arg-type]
            cost_usd=0.001,
            latency_ms=10,
            cache_read_tokens=0,
            cache_write_tokens=0,
        )

    return _stub


def _setup_mocks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSALPHA_MOCK_DATA", "1")
    from newsalpha.agents import news_collector as nc_mod
    from newsalpha.data.connectors.market import MockMarketDataConnector
    from newsalpha.data.connectors.news import MockNewsConnector

    monkeypatch.setattr(nc_mod, "_news", MockNewsConnector())
    monkeypatch.setattr(nc_mod, "_market", MockMarketDataConnector())
    monkeypatch.setattr(technical_analyst, "_market", MockMarketDataConnector())

    # Analyst layer — neutral panel
    monkeypatch.setattr(
        sentiment_analyst, "call_agent",
        _fake({"polarity": 0.5, "confidence": 0.7, "rationale": "x"}),
    )
    monkeypatch.setattr(
        fundamental_analyst, "call_agent",
        _fake({
            "scores": {"growth": 7.0, "margin": 6.0, "cash": 6.0, "leverage": 5.0, "valuation": 5.0},
            "event_driven": True, "rationale": "ok", "citations": [],
        }),
    )
    monkeypatch.setattr(
        technical_analyst, "call_agent",
        _fake({"signals": [], "overall_bias": "long", "overall_strength": 0.6, "rationale": "x"}),
    )


def test_w3_full_path_trade_executed(monkeypatch: pytest.MonkeyPatch) -> None:
    """High-conviction bull verdict → Trader emits buy → RiskManager accepts."""
    _setup_mocks(monkeypatch)

    monkeypatch.setattr(
        bull_researcher, "call_agent",
        _fake({
            "round": 1, "stance": "bull", "thesis_summary": "structural beat",
            "claims": [{"id": "B1", "claim": "x", "evidence": ["e"], "confidence": 0.7}],
            "conviction": 0.75,
        }),
    )
    monkeypatch.setattr(
        bear_researcher, "call_agent",
        _fake({
            "round": 1, "stance": "bear", "thesis_summary": "weak rebut",
            "claims": [{"id": "X1", "claim": "y", "evidence": ["e"], "confidence": 0.3}],
            "conviction": 0.3,
        }),
    )
    monkeypatch.setattr(
        debate_judge, "call_agent",
        _fake({
            "winner": "bull", "directional_bias": "long",
            "conviction": 0.72, "verdict_rationale": "bull won decisively",
        }),
    )
    monkeypatch.setattr(
        trader, "call_agent",
        _fake({
            "action": "buy", "ticker": "AAPL", "side": "long",
            "conviction": 0.7, "suggested_size_pct": 0.04,
            "entry_price_hint": 200.0, "stop_loss_price": 192.0,
            "take_profit_price": 216.0, "thesis_one_liner": "buy AAPL",
            "decisive_signals": ["B1"], "risks": [], "expected_holding_days": 10,
        }),
    )

    graph = build_graph()
    initial: TradingState = {
        "trigger": {"type": "test", "since": ""},
        "ticker": "AAPL",
        "as_of": datetime.now(tz=UTC).isoformat(),
        "trace_id": "test-w3-trade",
        "cost_usd": 0.0,
        "latency_ms": 0,
        "bull_arguments": [],
        "bear_arguments": [],
        "final_orders": [],
        "errors": [],
    }

    out = graph.invoke(initial)

    # Two debate rounds completed (bull+bear ran twice each).
    assert len(out["bull_arguments"]) == 2
    assert len(out["bear_arguments"]) == 2

    # Judge fired and gave a long verdict.
    assert out["judge_verdict"]["directional_bias"] == "long"

    # Trader's signal made it through, RiskManager accepted, order produced.
    assert out["trade_signal"]["action"] == "buy"
    assert out["risk_decision"]["accepted"] is True
    assert len(out["final_orders"]) == 1
    assert out["final_orders"][0]["ticker"] == "AAPL"


def test_w3_low_conviction_routes_to_log_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutral judge verdict → log_only branch → no trader / no orders."""
    _setup_mocks(monkeypatch)

    monkeypatch.setattr(
        bull_researcher, "call_agent",
        _fake({"round": 1, "stance": "bull", "claims": [], "conviction": 0.3}),
    )
    monkeypatch.setattr(
        bear_researcher, "call_agent",
        _fake({"round": 1, "stance": "bear", "claims": [], "conviction": 0.3}),
    )
    monkeypatch.setattr(
        debate_judge, "call_agent",
        _fake({
            "winner": "neutral", "directional_bias": "neutral",
            "conviction": 0.4, "verdict_rationale": "evidence too thin",
        }),
    )

    # Trader stub MUST NOT be hit — assert by raising if called.
    def trader_should_not_run(*a: Any, **k: Any) -> LLMCallResult:
        raise AssertionError("Trader was called despite low judge conviction")

    monkeypatch.setattr(trader, "call_agent", trader_should_not_run)

    graph = build_graph()
    initial: TradingState = {
        "trigger": {"type": "test", "since": ""},
        "ticker": "AAPL",
        "as_of": datetime.now(tz=UTC).isoformat(),
        "trace_id": "test-w3-stop",
        "cost_usd": 0.0,
        "bull_arguments": [],
        "bear_arguments": [],
        "final_orders": [],
        "errors": [],
    }

    out = graph.invoke(initial)

    assert out["judge_verdict"]["directional_bias"] == "neutral"
    assert out.get("trade_signal") is None  # trader never set it
    assert out.get("risk_decision") is None
    assert out["final_orders"] == []
