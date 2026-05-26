from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from newsalpha.data.connectors.market import MockMarketDataConnector
from newsalpha.data.connectors.news import MockNewsConnector


def test_mock_news_connector_returns_one_item() -> None:
    items = MockNewsConnector().fetch(
        "AAPL",
        since_iso="2026-05-20T00:00:00+00:00",
        until_iso="2026-05-26T00:00:00+00:00",
    )
    assert len(items) == 1
    assert items[0].ticker == "AAPL"
    assert items[0].source == "mock"


def test_mock_market_snapshot_is_deterministic() -> None:
    c = MockMarketDataConnector()
    a = c.snapshot("AAPL", as_of_iso="2026-05-26T00:00:00+00:00")
    b = c.snapshot("AAPL", as_of_iso="2026-05-26T00:00:00+00:00")
    assert a.price == b.price
    assert a.high > a.low
    assert a.volume > 0


def test_mock_market_history_shape() -> None:
    df = MockMarketDataConnector().history(
        "AAPL", as_of_iso="2026-05-26T00:00:00+00:00", lookback_days=60
    )
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 60
    assert {"open", "high", "low", "close", "volume"} <= set(df.columns)
    assert (df["high"] >= df["low"]).all()


def test_mock_market_no_lookahead() -> None:
    """`as_of_iso` must bound the index from above."""
    as_of = "2026-05-26T00:00:00+00:00"
    df = MockMarketDataConnector().history("AAPL", as_of_iso=as_of, lookback_days=10)
    assert df.index.max() <= pd.Timestamp(as_of).normalize()
