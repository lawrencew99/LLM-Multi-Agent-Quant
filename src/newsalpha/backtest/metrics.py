"""Backtest performance metrics — computed in pure Python/numpy.

These are also what quantstats computes; we keep a slim in-process version
so unit tests don't need a full quantstats install path.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def sharpe_ratio(returns: pd.Series, rf: float = 0.0, periods: int = 252) -> float:
    """Annualized Sharpe ratio."""
    if returns.empty:
        return 0.0
    excess = returns - rf / periods
    std = float(excess.std())
    if not math.isfinite(std) or std < 1e-12:
        return 0.0
    return float(excess.mean() / std * math.sqrt(periods))


def sortino_ratio(returns: pd.Series, rf: float = 0.0, periods: int = 252) -> float:
    """Annualized Sortino ratio (downside deviation)."""
    if returns.empty:
        return 0.0
    excess = returns - rf / periods
    downside = excess[excess < 0]
    if downside.empty or downside.std() == 0:
        return float("inf") if excess.mean() > 0 else 0.0
    return float(excess.mean() / downside.std() * math.sqrt(periods))


def max_drawdown(returns: pd.Series) -> float:
    """Maximum peak-to-trough drawdown (negative number)."""
    if returns.empty:
        return 0.0
    cumulative = (1 + returns).cumprod()
    peak = cumulative.expanding().max()
    dd = (cumulative - peak) / peak
    return float(dd.min())


def cagr(returns: pd.Series, periods: int = 252) -> float:
    """Compound annual growth rate."""
    if returns.empty:
        return 0.0
    total = (1 + returns).prod()
    n_years = len(returns) / periods
    if n_years <= 0 or total <= 0:
        return 0.0
    return float(total ** (1 / n_years) - 1)


def win_rate(trade_log: list[dict]) -> float:
    """Fraction of trades with positive PnL."""
    if not trade_log:
        return 0.0
    wins = sum(1 for t in trade_log if t.get("pnl_pct", 0) > 0)
    return wins / len(trade_log)


def profit_factor(trade_log: list[dict]) -> float:
    """Gross profit / gross loss."""
    gross_profit = sum(t["pnl_pct"] for t in trade_log if t.get("pnl_pct", 0) > 0)
    gross_loss = abs(sum(t["pnl_pct"] for t in trade_log if t.get("pnl_pct", 0) < 0))
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def alpha_vs_benchmark(
    strategy_returns: pd.Series,
    benchmark_returns: pd.Series,
    periods: int = 252,
) -> float:
    """Annualized alpha vs benchmark (simple excess return)."""
    strat_cagr = cagr(strategy_returns, periods)
    bench_cagr = cagr(benchmark_returns, periods)
    return strat_cagr - bench_cagr


def compute_all_metrics(
    returns: pd.Series,
    trade_log: list[dict],
    benchmark_returns: pd.Series | None = None,
) -> dict[str, float]:
    """Compute the full metrics suite for a backtest run."""
    metrics = {
        "sharpe_ratio": sharpe_ratio(returns),
        "sortino_ratio": sortino_ratio(returns),
        "max_drawdown": max_drawdown(returns),
        "cagr": cagr(returns),
        "win_rate": win_rate(trade_log),
        "profit_factor": profit_factor(trade_log),
        "total_trades": len(trade_log),
        "total_return_pct": float((1 + returns).prod() - 1) * 100 if not returns.empty else 0.0,
    }

    if benchmark_returns is not None and not benchmark_returns.empty:
        metrics["alpha_vs_benchmark"] = alpha_vs_benchmark(returns, benchmark_returns)
        metrics["benchmark_return_pct"] = float((1 + benchmark_returns).prod() - 1) * 100

    return metrics
