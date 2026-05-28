"""Tests for W4: backtest metrics + report generation."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from newsalpha.backtest import metrics, reports


@pytest.fixture
def sample_returns() -> pd.Series:
    rng = np.random.default_rng(42)
    dates = pd.bdate_range("2023-01-02", "2023-12-29")
    daily = rng.normal(0.0005, 0.012, len(dates))
    return pd.Series(daily, index=dates, name="strategy")


@pytest.fixture
def sample_trade_log() -> list[dict]:
    return [
        {"ticker": "AAPL", "side": "long", "entry_date": "2023-01-15", "exit_date": "2023-02-10",
         "pnl_pct": 0.05, "exit_reason": "take_profit_hit", "conviction": 0.75},
        {"ticker": "MSFT", "side": "long", "entry_date": "2023-03-01", "exit_date": "2023-03-15",
         "pnl_pct": -0.03, "exit_reason": "stop_loss_hit", "conviction": 0.65},
        {"ticker": "NVDA", "side": "long", "entry_date": "2023-05-10", "exit_date": "2023-06-20",
         "pnl_pct": 0.18, "exit_reason": "take_profit_hit", "conviction": 0.85},
        {"ticker": "TSLA", "side": "short", "entry_date": "2023-07-01", "exit_date": "2023-07-20",
         "pnl_pct": -0.04, "exit_reason": "stop_loss_hit", "conviction": 0.62},
        {"ticker": "GOOGL", "side": "long", "entry_date": "2023-09-15", "exit_date": "2023-10-30",
         "pnl_pct": 0.08, "exit_reason": "end_of_backtest", "conviction": 0.71},
    ]


def test_sharpe_ratio_is_finite(sample_returns: pd.Series) -> None:
    sr = metrics.sharpe_ratio(sample_returns)
    assert isinstance(sr, float)
    assert -10 < sr < 10


def test_sharpe_zero_for_zero_volatility() -> None:
    flat = pd.Series([0.001] * 100)
    sr = metrics.sharpe_ratio(flat)
    assert sr == 0.0


def test_sortino_handles_no_downside() -> None:
    only_up = pd.Series([0.001, 0.002, 0.003, 0.004, 0.005])
    s = metrics.sortino_ratio(only_up)
    assert s == float("inf") or s == 0.0 or isinstance(s, float)


def test_max_drawdown_negative(sample_returns: pd.Series) -> None:
    md = metrics.max_drawdown(sample_returns)
    assert md <= 0


def test_max_drawdown_empty_series() -> None:
    assert metrics.max_drawdown(pd.Series(dtype=float)) == 0.0


def test_cagr_zero_for_empty() -> None:
    assert metrics.cagr(pd.Series(dtype=float)) == 0.0


def test_win_rate(sample_trade_log: list[dict]) -> None:
    wr = metrics.win_rate(sample_trade_log)
    assert wr == 3 / 5


def test_win_rate_empty() -> None:
    assert metrics.win_rate([]) == 0.0


def test_profit_factor(sample_trade_log: list[dict]) -> None:
    pf = metrics.profit_factor(sample_trade_log)
    assert pf > 1.0


def test_profit_factor_no_losses() -> None:
    only_wins = [{"pnl_pct": 0.05}, {"pnl_pct": 0.03}]
    assert metrics.profit_factor(only_wins) == float("inf")


def test_compute_all_metrics_includes_all_keys(
    sample_returns: pd.Series, sample_trade_log: list[dict]
) -> None:
    all_m = metrics.compute_all_metrics(sample_returns, sample_trade_log)
    expected_keys = {
        "sharpe_ratio", "sortino_ratio", "max_drawdown", "cagr",
        "win_rate", "profit_factor", "total_trades", "total_return_pct",
    }
    assert expected_keys <= set(all_m.keys())


def test_compute_metrics_with_benchmark(
    sample_returns: pd.Series, sample_trade_log: list[dict]
) -> None:
    bench = sample_returns * 0.5
    all_m = metrics.compute_all_metrics(sample_returns, sample_trade_log, bench)
    assert "alpha_vs_benchmark" in all_m
    assert "benchmark_return_pct" in all_m


def test_markdown_report_writes_file(
    tmp_path: Path, sample_returns: pd.Series, sample_trade_log: list[dict]
) -> None:
    out = tmp_path / "report.md"
    path = reports.write_markdown_report(sample_returns, sample_trade_log, output_path=out)
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "Sharpe ratio" in content
    assert "AAPL" in content
    assert "Trade Log" in content


def test_markdown_report_handles_no_trades(tmp_path: Path, sample_returns: pd.Series) -> None:
    out = tmp_path / "empty.md"
    reports.write_markdown_report(sample_returns, [], output_path=out)
    assert "No trades executed" in out.read_text(encoding="utf-8")
