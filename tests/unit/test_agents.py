"""Test agent nodes via mocked LLM calls — no real API traffic."""

from __future__ import annotations

from typing import Any

import pytest

from newsalpha.agents import fundamental_analyst, sentiment_analyst, technical_analyst
from newsalpha.core.state import TradingState
from newsalpha.llm.client import LLMCallResult


def _fake_result(parsed: dict[str, Any] | None, *, text: str = "{}") -> LLMCallResult:
    """Build a stub LLMCallResult that bypasses the real Anthropic client."""
    return LLMCallResult(
        text=text,
        parsed=parsed,
        raw_message=None,  # type: ignore[arg-type]
        cost_usd=0.001,
        latency_ms=42,
        cache_read_tokens=0,
        cache_write_tokens=0,
    )


def _base_state() -> TradingState:
    return {
        "trigger": {"type": "test", "since": ""},
        "ticker": "AAPL",
        "as_of": "2026-05-26T00:00:00+00:00",
        "news_items": [
            {
                "event_id": "fake-1",
                "ticker": "AAPL",
                "headline": "AAPL beats Q1 estimates by 12%",
                "summary": "Revenue $98B, EPS $1.65 — both above consensus.",
                "source": "test",
                "published_at": "2026-05-25T14:00:00+00:00",
                "category": "earnings",
                "url": "",
                "sentiment_hint": None,
            }
        ],
        "market_snapshot": {"ticker": "AAPL", "price": 200.0},
        "trace_id": "test",
        "debate_round": 0,
        "debate_mode": "adversarial",
        "cost_usd": 0.0,
        "latency_ms": 0,
        "bull_arguments": [],
        "bear_arguments": [],
        "final_orders": [],
        "errors": [],
    }


def test_sentiment_analyst_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _fake_result(
        {"polarity": 0.6, "confidence": 0.8, "horizon": "days", "rationale": "ok"}
    )
    monkeypatch.setattr(sentiment_analyst, "call_agent", lambda *a, **k: fake)

    out = sentiment_analyst.sentiment_analyst(_base_state())

    assert out["sentiment_report"]["polarity"] == 0.6
    assert out["cost_usd"] == pytest.approx(0.001)


def test_sentiment_analyst_parse_failure_uses_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _fake_result(parsed=None, text="LLM returned non-JSON garbage")
    monkeypatch.setattr(sentiment_analyst, "call_agent", lambda *a, **k: fake)

    out = sentiment_analyst.sentiment_analyst(_base_state())

    assert out["sentiment_report"]["polarity"] == 0.0
    assert out["sentiment_report"]["parse_failed"] is True


def test_sentiment_analyst_exception_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*a: Any, **k: Any) -> LLMCallResult:
        raise RuntimeError("api blew up")

    monkeypatch.setattr(sentiment_analyst, "call_agent", boom)

    out = sentiment_analyst.sentiment_analyst(_base_state())

    assert "error" in out["sentiment_report"]
    assert any("sentiment_analyst" in e for e in out["errors"])


def test_fundamental_analyst_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _fake_result(
        {
            "scores": {
                "growth": 8.0,
                "margin": 6.5,
                "cash": 7.0,
                "leverage": 5.5,
                "valuation": 6.0,
            },
            "event_driven": True,
            "rationale": "Strong Q1 beat",
            "citations": ["AAPL beats Q1 estimates by 12%"],
        }
    )
    monkeypatch.setattr(fundamental_analyst, "call_agent", lambda *a, **k: fake)

    out = fundamental_analyst.fundamental_analyst(_base_state())

    assert out["fundamental_report"]["scores"]["growth"] == 8.0
    assert out["fundamental_report"]["event_driven"] is True


def test_fundamental_analyst_exception_returns_neutral(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*a: Any, **k: Any) -> LLMCallResult:
        raise RuntimeError("fail")

    monkeypatch.setattr(fundamental_analyst, "call_agent", boom)

    out = fundamental_analyst.fundamental_analyst(_base_state())

    # All five dimensions should default to the 5.0 neutral baseline.
    assert all(v == 5.0 for v in out["fundamental_report"]["scores"].values())


def test_technical_analyst_attaches_panel(monkeypatch: pytest.MonkeyPatch) -> None:
    """Even on parse failure, the deterministic indicator panel must be returned."""
    monkeypatch.setenv("NEWSALPHA_MOCK_DATA", "1")

    fake = _fake_result(parsed=None, text="not json")
    monkeypatch.setattr(technical_analyst, "call_agent", lambda *a, **k: fake)

    # Force the module-level connector to refresh now that env var is set.
    from newsalpha.data.connectors.market import MockMarketDataConnector

    monkeypatch.setattr(technical_analyst, "_market", MockMarketDataConnector())

    out = technical_analyst.technical_analyst(_base_state())

    assert "panel" in out["technical_report"]
    assert out["technical_report"]["panel"]["n_bars"] >= 30
