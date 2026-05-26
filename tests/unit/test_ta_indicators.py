from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from newsalpha.tools.ta import indicators


@pytest.fixture
def linear_bars() -> pd.DataFrame:
    """100 sessions, monotonically rising close — a clean trend test fixture."""
    n = 100
    closes = np.linspace(100.0, 130.0, n)
    return pd.DataFrame(
        {
            "open": closes - 0.5,
            "high": closes + 1.0,
            "low": closes - 1.0,
            "close": closes,
            "volume": np.full(n, 1_000_000),
        },
        index=pd.bdate_range("2024-01-01", periods=n),
    )


def test_rsi_in_unit_range(linear_bars: pd.DataFrame) -> None:
    rsi = indicators.rsi(linear_bars["close"]).dropna()
    assert (rsi >= 0).all() and (rsi <= 100).all()
    # Pure uptrend should pin RSI near the upper bound.
    assert rsi.iloc[-1] > 90


def test_macd_components_exist(linear_bars: pd.DataFrame) -> None:
    line, signal, hist = indicators.macd(linear_bars["close"])
    assert len(line) == len(linear_bars)
    assert len(signal) == len(linear_bars)
    # On a steady uptrend the histogram is positive at the tail.
    assert hist.iloc[-1] > 0


def test_atr_positive(linear_bars: pd.DataFrame) -> None:
    a = indicators.atr(linear_bars["high"], linear_bars["low"], linear_bars["close"])
    tail = a.dropna()
    assert (tail > 0).all()


def test_summarize_minimum_bars() -> None:
    """Empty / too-short bars must return a None-padded panel, not crash."""
    panel = indicators.summarize(pd.DataFrame())
    assert panel["price"] is None
    assert panel["n_bars"] == 0


def test_summarize_full_panel(linear_bars: pd.DataFrame) -> None:
    panel = indicators.summarize(linear_bars)
    assert panel["price"] is not None
    assert panel["rsi14"] is not None
    assert panel["atr14"] is not None
    assert panel["trend_20"] is not None
    assert panel["trend_20"] > 0  # uptrend


def test_support_resistance_ordering(linear_bars: pd.DataFrame) -> None:
    s, r = indicators.support_resistance(linear_bars["close"])
    assert s < r
