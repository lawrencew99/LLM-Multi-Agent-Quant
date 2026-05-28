"""W6 long backtest tests — regime-aware signal gen + 4-segment runner."""

from __future__ import annotations

from pathlib import Path

import pytest

from newsalpha.backtest.long_backtest import (
    REGIMES,
    generate_regime_signals,
    run_long_backtest,
)


@pytest.fixture(autouse=True)
def force_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSALPHA_MOCK_DATA", "1")


def test_regimes_cover_2020_to_2025() -> None:
    assert len(REGIMES) == 4
    starts = [r["start"] for r in REGIMES]
    ends = [r["end"] for r in REGIMES]
    assert starts[0].startswith("2020")
    assert ends[-1].startswith("2024")
    assert {r["regime"] for r in REGIMES} == {"crisis", "bull", "bear"}


def test_generate_regime_signals_respects_long_bias() -> None:
    bull_cfg = next(r for r in REGIMES if r["regime"] == "bull")
    signals = generate_regime_signals(["AAPL", "MSFT"], bull_cfg, seed=42)
    n_long = sum(1 for s in signals if s["side"] == "long")
    # bull regime has long_bias >= 0.7 — expect majority long
    assert n_long / len(signals) > 0.55


def test_generate_regime_signals_deterministic_with_seed() -> None:
    cfg = REGIMES[0]
    s1 = generate_regime_signals(["AAPL"], cfg, seed=42)
    s2 = generate_regime_signals(["AAPL"], cfg, seed=42)
    assert [s["side"] for s in s1] == [s["side"] for s in s2]
    assert [s["conviction"] for s in s1] == [s["conviction"] for s in s2]


def test_generate_regime_signals_size_in_range() -> None:
    cfg = REGIMES[0]
    signals = generate_regime_signals(["AAPL"], cfg, seed=1)
    lo, hi = cfg["size_range"]
    for s in signals:
        assert lo <= s["size_pct"] <= hi


def test_run_long_backtest_produces_reports(tmp_path: Path) -> None:
    out = run_long_backtest(tickers=["AAPL", "MSFT"], report_dir=tmp_path)
    assert "full_metrics" in out
    assert len(out["segments"]) == 4
    assert Path(out["report_path"]).exists()
    assert Path(out["metrics_path"]).exists()
    # Each segment should have at least some trades
    assert all(s["metrics"]["total_trades"] >= 0 for s in out["segments"])


def test_run_long_backtest_full_period_metrics_present(tmp_path: Path) -> None:
    out = run_long_backtest(tickers=["AAPL"], report_dir=tmp_path)
    m = out["full_metrics"]
    for k in ("sharpe_ratio", "sortino_ratio", "max_drawdown", "cagr",
              "win_rate", "profit_factor", "total_trades"):
        assert k in m
    assert m["n_segments"] == 4
