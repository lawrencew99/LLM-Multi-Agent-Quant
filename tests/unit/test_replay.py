"""Tests for W4: backtest replay + extract_signals_for_backtest."""

from __future__ import annotations

import json
from pathlib import Path

from newsalpha.backtest import replay, snapshots


def _make_snapshot(tmp_path: Path, *, ticker: str, accepted: bool, side: str = "long") -> Path:
    state = {
        "trace_id": f"test-{ticker}",
        "ticker": ticker,
        "as_of": "2023-06-15T00:00:00Z",
        "trade_signal": {
            "action": "buy" if accepted else "hold",
            "ticker": ticker,
            "side": side if accepted else "flat",
            "suggested_size_pct": 0.04,
            "entry_price_hint": 150.0,
            "stop_loss_price": 145.0 if side == "long" else 155.0,
            "take_profit_price": 165.0 if side == "long" else 135.0,
            "thesis_one_liner": "test signal",
        } if accepted else {"action": "hold", "ticker": ticker, "side": "flat"},
        "market_snapshot": {"price": 150.0, "atr14": 2.5},
        "judge_verdict": {"directional_bias": side, "conviction": 0.75 if accepted else 0.4},
        "risk_decision": {
            "accepted": accepted,
            "final_size_pct": 0.04 if accepted else 0.0,
            "final_stop_price": 145.0 if accepted and side == "long" else 0.0,
            "reasons": ["accepted"] if accepted else ["trader_recommended_hold"],
        },
        "final_orders": [{
            "ticker": ticker,
            "side": side,
            "size_pct": 0.04,
            "stop_loss_price": 145.0 if side == "long" else 155.0,
            "take_profit_price": 165.0 if side == "long" else 135.0,
            "entry_price_hint": 150.0,
            "thesis": "test",
        }] if accepted else [],
    }
    return snapshots.write_snapshot(state, snapshot_dir=tmp_path)


def test_replay_unchanged_with_no_overrides(tmp_path: Path) -> None:
    snap_path = _make_snapshot(tmp_path, ticker="AAPL", accepted=True)
    replayed = replay.replay_decision(snap_path)
    assert replayed["risk_decision"]["accepted"] is True
    assert len(replayed["final_orders"]) == 1


def test_replay_with_strict_risk_config_rejects(tmp_path: Path) -> None:
    snap_path = _make_snapshot(tmp_path, ticker="AAPL", accepted=True)

    strict_config = {
        "position": {"max_single_pct": 0.001},
        "stops": {"atr_multiplier": 2.0},
        "universe_filter": {"min_avg_dollar_volume_usd": 0},
    }
    replayed = replay.replay_decision(snap_path, override_risk_config=strict_config)
    assert replayed["risk_decision"]["final_size_pct"] <= 0.001


def test_extract_signals_only_includes_accepted(tmp_path: Path) -> None:
    _make_snapshot(tmp_path, ticker="AAPL", accepted=True)
    _make_snapshot(tmp_path, ticker="MSFT", accepted=False)
    _make_snapshot(tmp_path, ticker="NVDA", accepted=True, side="short")

    signals = replay.extract_signals_for_backtest(tmp_path)
    tickers = {s["ticker"] for s in signals}
    assert "AAPL" in tickers
    assert "NVDA" in tickers
    assert "MSFT" not in tickers


def test_extract_signals_handles_corrupt_snapshot(tmp_path: Path) -> None:
    _make_snapshot(tmp_path, ticker="AAPL", accepted=True)
    (tmp_path / "broken.json").write_text("{not valid json", encoding="utf-8")
    signals = replay.extract_signals_for_backtest(tmp_path)
    assert any(s["ticker"] == "AAPL" for s in signals)


def test_extract_signals_empty_dir(tmp_path: Path) -> None:
    signals = replay.extract_signals_for_backtest(tmp_path / "missing")
    assert signals == []
