"""W5 tests for execution layer (broker + sizing) and graph extension."""

from __future__ import annotations

import pytest

from newsalpha.execution.broker import (
    AccountSummary,
    BaseBroker,
    MockBroker,
    OrderResult,
    Position,
)
from newsalpha.execution.sizing import (
    compute_final_size,
    conviction_scaled_size,
    fractional_kelly,
    vol_target_size,
)


def test_mock_broker_buy_creates_position() -> None:
    b = MockBroker(starting_cash=10_000)
    result = b.submit_order("AAPL", qty=10, side="buy", limit_price=150.0)
    assert result.status == "filled"
    assert result.broker == "mock"
    positions = b.get_positions()
    assert len(positions) == 1
    assert positions[0].ticker == "AAPL"
    assert positions[0].qty == 10


def test_mock_broker_sell_reduces_position() -> None:
    b = MockBroker(starting_cash=10_000)
    b.submit_order("AAPL", qty=10, side="buy", limit_price=150.0)
    b.submit_order("AAPL", qty=5, side="sell", limit_price=160.0)
    positions = b.get_positions()
    assert len(positions) == 1
    assert positions[0].qty == 5


def test_mock_broker_full_close_removes_position() -> None:
    b = MockBroker(starting_cash=10_000)
    b.submit_order("AAPL", qty=10, side="buy", limit_price=150.0)
    b.submit_order("AAPL", qty=10, side="sell", limit_price=160.0)
    assert b.get_positions() == []


def test_mock_broker_account_summary() -> None:
    b = MockBroker(starting_cash=10_000)
    b.submit_order("AAPL", qty=10, side="buy", limit_price=100.0)
    acc = b.get_account()
    assert isinstance(acc, AccountSummary)
    assert acc.cash == 9_000
    assert acc.portfolio_value == 10_000  # cash + 10 shares * $100 mkt


def test_mock_broker_logs_orders() -> None:
    b = MockBroker()
    b.submit_order("AAPL", 10, "buy", limit_price=100)
    b.submit_order("MSFT", 5, "buy", limit_price=200)
    assert len(b.order_log) == 2
    assert b.order_log[0].ticker == "AAPL"
    assert b.order_log[1].ticker == "MSFT"


def test_alpaca_broker_refuses_live_without_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    from newsalpha.core.config import get_settings

    monkeypatch.setattr(get_settings.__wrapped__, "__call__", lambda: None, raising=False)
    monkeypatch.setenv("BROKER_MODE", "live")
    monkeypatch.setenv("ALPACA_API_KEY", "fake")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "fake")
    get_settings.cache_clear()

    from newsalpha.execution.broker import AlpacaBroker

    with pytest.raises(RuntimeError, match="confirm_live"):
        AlpacaBroker(confirm_live=False)


def test_get_default_broker_falls_back_to_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSALPHA_BROKER", "mock")
    from newsalpha.execution.broker import get_default_broker
    b = get_default_broker()
    assert isinstance(b, MockBroker)


# ── Sizing ──────────────────────────────────────────────────────────────


def test_fractional_kelly_negative_edge_returns_zero() -> None:
    assert fractional_kelly(p_win=0.4, win_loss_ratio=1.0) == 0.0


def test_fractional_kelly_positive_edge_returns_positive() -> None:
    f = fractional_kelly(p_win=0.6, win_loss_ratio=2.0, fraction=0.25)
    assert 0 < f <= 0.25


def test_fractional_kelly_invalid_inputs() -> None:
    assert fractional_kelly(p_win=0.0, win_loss_ratio=1.0) == 0.0
    assert fractional_kelly(p_win=1.0, win_loss_ratio=1.0) == 0.0
    assert fractional_kelly(p_win=0.6, win_loss_ratio=0.0) == 0.0


def test_vol_target_clips_to_bounds() -> None:
    assert vol_target_size(0.05, asset_vol=0.01) == 0.05 * 1.5
    assert vol_target_size(0.05, asset_vol=1.0) == 0.05 * 0.25


def test_vol_target_zero_vol_returns_base() -> None:
    assert vol_target_size(0.05, asset_vol=0.0) == 0.05


def test_conviction_scaled_size_below_threshold_zero() -> None:
    assert conviction_scaled_size(0.05, conviction=0.5) == 0.0


def test_conviction_scaled_size_at_max() -> None:
    assert conviction_scaled_size(0.05, conviction=1.0) == 0.05


def test_compute_final_size_returns_breakdown() -> None:
    result = compute_final_size(
        0.05, conviction=0.8, asset_vol=0.20, p_win=0.55, win_loss_ratio=1.5,
    )
    assert "final_size_pct" in result
    assert "kelly_factor" in result
    assert "vol_factor" in result
    assert result["final_size_pct"] <= 0.05


def test_compute_final_size_caps_at_max() -> None:
    result = compute_final_size(0.10, conviction=1.0, max_single_pct=0.05)
    assert result["final_size_pct"] <= 0.05
