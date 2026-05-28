"""Tests for W4 backtest engine — runs through mocked market data."""

from __future__ import annotations

import os

import pandas as pd
import pytest

from newsalpha.backtest import engine


@pytest.fixture(autouse=True)
def force_mock_market(monkeypatch: pytest.MonkeyPatch) -> None:
    """All backtest tests use the deterministic mock market data."""
    monkeypatch.setenv("NEWSALPHA_MOCK_DATA", "1")
    from newsalpha.data.connectors import market as market_mod
    monkeypatch.setattr(
        market_mod,
        "get_default_market_connector",
        market_mod.MockMarketDataConnector,
    )
    import newsalpha.backtest.engine as engine_mod
    monkeypatch.setattr(
        engine_mod,
        "get_default_market_connector",
        market_mod.MockMarketDataConnector,
    )


def _sample_signals(ticker: str = "AAPL") -> list[dict]:
    return [
        {
            "ticker": ticker,
            "as_of": "2023-02-15T00:00:00Z",
            "side": "long",
            "size_pct": 0.04,
            "entry_price": 100.0,
            "stop_loss": 90.0,
            "take_profit": 115.0,
            "conviction": 0.75,
            "trace_id": "sig1",
        },
        {
            "ticker": ticker,
            "as_of": "2023-06-15T00:00:00Z",
            "side": "long",
            "size_pct": 0.03,
            "entry_price": 105.0,
            "stop_loss": 95.0,
            "take_profit": 120.0,
            "conviction": 0.80,
            "trace_id": "sig2",
        },
    ]


def test_backtest_runs_without_error() -> None:
    signals = _sample_signals("AAPL")
    result = engine.run_backtest(
        "AAPL", signals,
        start_date="2023-01-02",
        end_date="2023-12-29",
    )
    assert "error" not in result
    assert "portfolio_values" in result
    assert result["initial_cash"] > 0
    assert isinstance(result["trade_log"], list)


def test_backtest_filters_signals_by_ticker() -> None:
    signals = _sample_signals("AAPL") + _sample_signals("MSFT")
    result = engine.run_backtest(
        "AAPL", signals,
        start_date="2023-01-02",
        end_date="2023-12-29",
    )
    for trade in result["trade_log"]:
        assert trade["ticker"] == "AAPL"


def test_backtest_empty_signals_no_trades() -> None:
    result = engine.run_backtest(
        "AAPL", [],
        start_date="2023-01-02",
        end_date="2023-06-30",
    )
    assert result["n_trades"] == 0
    assert result["trade_log"] == []


def test_multi_ticker_backtest_aggregates() -> None:
    signals = _sample_signals("AAPL") + _sample_signals("MSFT")
    result = engine.run_multi_ticker_backtest(
        ["AAPL", "MSFT"], signals,
        start_date="2023-01-02",
        end_date="2023-12-29",
    )
    assert "combined_returns" in result
    assert "per_ticker" in result
    assert len(result["per_ticker"]) == 2
    assert isinstance(result["combined_returns"], pd.Series)


def test_strategy_records_exit_reason() -> None:
    signals = [{
        "ticker": "AAPL",
        "as_of": "2023-02-01T00:00:00Z",
        "side": "long",
        "size_pct": 0.04,
        "entry_price": 100.0,
        "stop_loss": 99.0,
        "take_profit": 101.0,
        "conviction": 0.75,
        "trace_id": "tight",
    }]
    result = engine.run_backtest(
        "AAPL", signals,
        start_date="2023-01-02",
        end_date="2023-12-29",
    )
    for trade in result["trade_log"]:
        assert trade["exit_reason"] in (
            "stop_loss_hit", "take_profit_hit", "end_of_backtest"
        )
