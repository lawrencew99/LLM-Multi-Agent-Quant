"""Tests for the W3 debate + decision agents (Bull/Bear/Judge/Trader/RiskManager)."""

from __future__ import annotations

from typing import Any

import pytest

from newsalpha.agents import (
    bear_researcher,
    bull_researcher,
    debate_judge,
    debate_orchestrator,
    risk_manager,
    trader,
)
from newsalpha.core.state import TradingState
from newsalpha.llm.client import LLMCallResult


def _fake_result(parsed: dict[str, Any] | None, *, text: str = "{}") -> LLMCallResult:
    return LLMCallResult(
        text=text,
        parsed=parsed,
        raw_message=None,  # type: ignore[arg-type]
        cost_usd=0.002,
        latency_ms=99,
        cache_read_tokens=0,
        cache_write_tokens=0,
    )


def _state_with_analyst_reports() -> TradingState:
    return {
        "ticker": "AAPL",
        "as_of": "2026-05-26T00:00:00+00:00",
        "news_items": [],
        "market_snapshot": {
            "ticker": "AAPL",
            "price": 200.0,
            "atr14": 4.0,
        },
        "sentiment_report": {"polarity": 0.5, "confidence": 0.7},
        "fundamental_report": {"scores": {"growth": 7.0}},
        "technical_report": {"panel": {"price": 200.0, "rsi14": 55.0}},
        "bull_arguments": [],
        "bear_arguments": [],
        "debate_round": 1,
        "debate_mode": "adversarial",
        "cost_usd": 0.0,
        "errors": [],
        "final_orders": [],
    }


# ── bull / bear / judge ─────────────────────────────────────────────────────────
def test_bull_emits_argument_with_round(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _fake_result(
        {
            "round": 1,
            "stance": "bull",
            "thesis_summary": "earnings beat is structural",
            "claims": [{"id": "B1", "claim": "x", "evidence": ["e1"], "confidence": 0.7}],
            "conviction": 0.7,
        }
    )
    monkeypatch.setattr(bull_researcher, "call_agent", lambda *a, **k: fake)

    out = bull_researcher.bull_researcher(_state_with_analyst_reports())

    assert isinstance(out["bull_arguments"], list)
    assert out["bull_arguments"][0]["stance"] == "bull"
    assert out["cost_usd"] == pytest.approx(0.002)


def test_bear_emits_argument_with_round(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _fake_result(
        {
            "round": 1,
            "stance": "bear",
            "thesis_summary": "valuation already prices it in",
            "claims": [{"id": "X1", "claim": "y", "evidence": ["e2"], "confidence": 0.6}],
            "conviction": 0.55,
        }
    )
    monkeypatch.setattr(bear_researcher, "call_agent", lambda *a, **k: fake)

    out = bear_researcher.bear_researcher(_state_with_analyst_reports())

    assert out["bear_arguments"][0]["stance"] == "bear"


def test_judge_returns_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _fake_result(
        {
            "winner": "bull",
            "directional_bias": "long",
            "conviction": 0.72,
            "verdict_rationale": "bull cases survived rebuttal",
        }
    )
    monkeypatch.setattr(debate_judge, "call_agent", lambda *a, **k: fake)

    out = debate_judge.debate_judge(_state_with_analyst_reports())

    assert out["judge_verdict"]["conviction"] == 0.72
    assert out["judge_verdict"]["directional_bias"] == "long"


# ── trader gating ───────────────────────────────────────────────────────────────
def test_trader_holds_when_conviction_low() -> None:
    state = _state_with_analyst_reports()
    state["judge_verdict"] = {
        "directional_bias": "long",
        "conviction": 0.4,  # below threshold
    }
    out = trader.trader(state)

    assert out["trade_signal"]["action"] == "hold"
    # Crucially, trader must NOT have called the LLM — no cost emitted.
    assert "cost_usd" not in out


def test_trader_holds_when_neutral() -> None:
    state = _state_with_analyst_reports()
    state["judge_verdict"] = {"directional_bias": "neutral", "conviction": 0.9}
    out = trader.trader(state)
    assert out["trade_signal"]["action"] == "hold"


def test_trader_emits_signal_when_high_conviction(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _fake_result(
        {
            "action": "buy",
            "ticker": "AAPL",
            "side": "long",
            "conviction": 0.7,
            "suggested_size_pct": 0.04,
            "entry_price_hint": 200.0,
            "stop_loss_price": 192.0,
            "take_profit_price": 216.0,
            "thesis_one_liner": "earnings momentum",
            "decisive_signals": ["B1"],
            "risks": ["macro"],
            "expected_holding_days": 10,
        }
    )
    monkeypatch.setattr(trader, "call_agent", lambda *a, **k: fake)

    state = _state_with_analyst_reports()
    state["judge_verdict"] = {"directional_bias": "long", "conviction": 0.7}
    out = trader.trader(state)

    assert out["trade_signal"]["action"] == "buy"
    assert out["trade_signal"]["suggested_size_pct"] == 0.04


# ── risk manager (deterministic) ────────────────────────────────────────────────
def test_risk_manager_accepts_clean_signal() -> None:
    state = _state_with_analyst_reports()
    state["trade_signal"] = {
        "action": "buy",
        "ticker": "AAPL",
        "side": "long",
        "suggested_size_pct": 0.03,
        "entry_price_hint": 200.0,
        "stop_loss_price": 192.0,
        "take_profit_price": 216.0,
        "thesis_one_liner": "ok",
    }
    out = risk_manager.risk_manager(state)

    assert out["risk_decision"]["accepted"] is True
    assert len(out["final_orders"]) == 1
    assert out["final_orders"][0]["size_pct"] == 0.03


def test_risk_manager_caps_oversized_signal() -> None:
    state = _state_with_analyst_reports()
    state["trade_signal"] = {
        "action": "buy",
        "ticker": "AAPL",
        "side": "long",
        "suggested_size_pct": 0.20,  # way over 5% cap
        "entry_price_hint": 200.0,
        "stop_loss_price": 192.0,
    }
    out = risk_manager.risk_manager(state)

    assert out["risk_decision"]["accepted"] is True
    assert out["risk_decision"]["final_size_pct"] == pytest.approx(0.05)
    assert any("size_capped" in a for a in out["risk_decision"]["adjustments"])


def test_risk_manager_backfills_stop_from_atr() -> None:
    state = _state_with_analyst_reports()
    state["trade_signal"] = {
        "action": "buy",
        "ticker": "AAPL",
        "side": "long",
        "suggested_size_pct": 0.03,
        "entry_price_hint": 200.0,
        "stop_loss_price": 0.0,  # missing — should be backfilled
    }
    out = risk_manager.risk_manager(state)

    assert out["risk_decision"]["accepted"] is True
    # 2 × ATR(14) = 8 → stop = 192
    assert out["risk_decision"]["final_stop_price"] == pytest.approx(192.0)


def test_risk_manager_rejects_long_with_stop_above_entry() -> None:
    state = _state_with_analyst_reports()
    state["trade_signal"] = {
        "action": "buy",
        "ticker": "AAPL",
        "side": "long",
        "suggested_size_pct": 0.03,
        "entry_price_hint": 200.0,
        "stop_loss_price": 210.0,  # invalid: above entry on a long
    }
    out = risk_manager.risk_manager(state)

    assert out["risk_decision"]["accepted"] is False
    assert "final_orders" not in out


def test_risk_manager_short_circuits_hold() -> None:
    state = _state_with_analyst_reports()
    state["trade_signal"] = {"action": "hold", "ticker": "AAPL", "side": "flat"}
    out = risk_manager.risk_manager(state)

    assert out["risk_decision"]["accepted"] is False
    assert "trader_recommended_hold" in out["risk_decision"]["reasons"]


# ── debate orchestration helpers ────────────────────────────────────────────────
def test_orchestrator_seeds_round_and_mode() -> None:
    state: TradingState = {"ticker": "AAPL"}
    out = debate_orchestrator.debate_orchestrator(state)
    assert out["debate_round"] == 1
    assert out["debate_mode"] in {"adversarial", "panel", "socratic"}


def test_orchestrator_noop_when_already_seeded() -> None:
    state: TradingState = {
        "ticker": "AAPL",
        "debate_round": 2,
        "debate_mode": "panel",
    }
    assert debate_orchestrator.debate_orchestrator(state) == {}


def test_round_advancer_increments() -> None:
    out = debate_orchestrator.debate_round_advancer({"debate_round": 1})  # type: ignore[arg-type]
    assert out["debate_round"] == 2


def test_should_continue_routes_correctly(monkeypatch: pytest.MonkeyPatch) -> None:
    # `debate_round` reflects the *next* round to run. With max_rounds=2:
    #   next=1 → continue (run round 1), next=2 → continue (run round 2),
    #   next=3 → judge (rounds 1 and 2 are done).
    s1: TradingState = {"debate_round": 1}  # type: ignore[typeddict-item]
    s2: TradingState = {"debate_round": 2}  # type: ignore[typeddict-item]
    s3: TradingState = {"debate_round": 3}  # type: ignore[typeddict-item]
    assert debate_orchestrator.should_continue_debate(s1) == "continue"
    assert debate_orchestrator.should_continue_debate(s2) == "continue"
    assert debate_orchestrator.should_continue_debate(s3) == "judge"


def test_should_trade_gates_on_conviction() -> None:
    high: TradingState = {  # type: ignore[typeddict-item]
        "judge_verdict": {"directional_bias": "long", "conviction": 0.7}
    }
    low: TradingState = {  # type: ignore[typeddict-item]
        "judge_verdict": {"directional_bias": "long", "conviction": 0.4}
    }
    neut: TradingState = {  # type: ignore[typeddict-item]
        "judge_verdict": {"directional_bias": "neutral", "conviction": 0.9}
    }
    assert debate_orchestrator.should_trade(high) == "trade"
    assert debate_orchestrator.should_trade(low) == "stop"
    assert debate_orchestrator.should_trade(neut) == "stop"
