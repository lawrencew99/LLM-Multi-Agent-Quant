"""Verify the W2 graph wiring without making real API calls."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from newsalpha.agents import fundamental_analyst, sentiment_analyst, technical_analyst
from newsalpha.core.graph import build_graph
from newsalpha.core.state import TradingState
from newsalpha.llm.client import LLMCallResult


def _fake_call(parsed: dict[str, Any]):
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


def test_w2_graph_runs_with_mocked_llms(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSALPHA_MOCK_DATA", "1")
    # Replace the connectors that were already captured at import time.
    from newsalpha.agents import news_collector as nc_mod
    from newsalpha.data.connectors.market import MockMarketDataConnector
    from newsalpha.data.connectors.news import MockNewsConnector

    monkeypatch.setattr(nc_mod, "_news", MockNewsConnector())
    monkeypatch.setattr(nc_mod, "_market", MockMarketDataConnector())
    monkeypatch.setattr(technical_analyst, "_market", MockMarketDataConnector())

    monkeypatch.setattr(
        sentiment_analyst,
        "call_agent",
        _fake_call({"polarity": 0.5, "confidence": 0.7, "rationale": "x"}),
    )
    monkeypatch.setattr(
        fundamental_analyst,
        "call_agent",
        _fake_call(
            {
                "scores": {
                    "growth": 6.0,
                    "margin": 5.0,
                    "cash": 5.0,
                    "leverage": 5.0,
                    "valuation": 5.0,
                },
                "event_driven": False,
                "rationale": "x",
                "citations": [],
            }
        ),
    )
    monkeypatch.setattr(
        technical_analyst,
        "call_agent",
        _fake_call(
            {
                "signals": [],
                "overall_bias": "neutral",
                "overall_strength": 0.3,
                "rationale": "x",
            }
        ),
    )

    graph = build_graph()
    initial: TradingState = {
        "trigger": {"type": "test", "since": ""},
        "ticker": "AAPL",
        "as_of": datetime.now(tz=UTC).isoformat(),
        "trace_id": "test-w2",
        "debate_round": 0,
        "debate_mode": "adversarial",
        "cost_usd": 0.0,
        "latency_ms": 0,
        "bull_arguments": [],
        "bear_arguments": [],
        "final_orders": [],
        "errors": [],
    }

    out = graph.invoke(initial)

    # All three analyst slots are populated.
    assert out["sentiment_report"]["polarity"] == 0.5
    assert out["fundamental_report"]["scores"]["growth"] == 6.0
    assert out["technical_report"]["overall_bias"] == "neutral"
    # Costs accumulated from all three analysts.
    assert out["cost_usd"] >= 0.003 - 1e-9
