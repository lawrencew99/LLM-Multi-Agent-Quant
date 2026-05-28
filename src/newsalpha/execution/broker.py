"""Broker abstraction — paper / live / mock variants.

Trust boundary contract:
  - All real-money mutations gate on `BROKER_MODE=live` AND explicit confirmation
  - Default is `paper` — Alpaca paper trading
  - Mock mode for unit tests; never touches network

The broker receives final orders only AFTER RiskManager has accepted them.
This module does NOT make trading decisions — it executes them.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from newsalpha.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class OrderResult:
    """Outcome of one order submission."""
    order_id: str
    ticker: str
    side: str
    qty: float
    requested_price: float | None
    status: str  # accepted | rejected | filled | partially_filled
    submitted_at: str
    broker: str
    error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Position:
    ticker: str
    qty: float
    avg_entry_price: float
    market_value: float
    unrealized_pnl: float
    side: str = "long"


@dataclass
class AccountSummary:
    cash: float
    portfolio_value: float
    buying_power: float
    daytrade_count: int = 0


class BaseBroker(ABC):
    name: str = "base"

    @abstractmethod
    def submit_order(
        self,
        ticker: str,
        qty: float,
        side: str,
        *,
        order_type: str = "market",
        limit_price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> OrderResult: ...

    @abstractmethod
    def get_positions(self) -> list[Position]: ...

    @abstractmethod
    def get_account(self) -> AccountSummary: ...

    @abstractmethod
    def cancel_all(self) -> None: ...


class MockBroker(BaseBroker):
    """In-memory broker for tests. No network. Deterministic order IDs."""

    name = "mock"

    def __init__(self, starting_cash: float = 100_000.0) -> None:
        self._cash = starting_cash
        self._starting_cash = starting_cash
        self._positions: dict[str, Position] = {}
        self._order_seq = 0
        self.order_log: list[OrderResult] = []

    def submit_order(
        self,
        ticker: str,
        qty: float,
        side: str,
        *,
        order_type: str = "market",
        limit_price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> OrderResult:
        self._order_seq += 1
        order_id = f"mock-{self._order_seq:06d}"
        price = limit_price if limit_price else 100.0  # arbitrary mock fill price

        existing = self._positions.get(ticker)
        if side == "buy":
            if existing is None:
                self._positions[ticker] = Position(
                    ticker=ticker, qty=qty, avg_entry_price=price,
                    market_value=qty * price, unrealized_pnl=0.0, side="long",
                )
            else:
                new_qty = existing.qty + qty
                new_avg = (existing.avg_entry_price * existing.qty + price * qty) / new_qty
                self._positions[ticker] = Position(
                    ticker=ticker, qty=new_qty, avg_entry_price=new_avg,
                    market_value=new_qty * price, unrealized_pnl=0.0, side="long",
                )
            self._cash -= qty * price
        elif side == "sell":
            if existing:
                if existing.qty > qty:
                    self._positions[ticker] = Position(
                        ticker=ticker, qty=existing.qty - qty,
                        avg_entry_price=existing.avg_entry_price,
                        market_value=(existing.qty - qty) * price,
                        unrealized_pnl=0.0, side="long",
                    )
                else:
                    del self._positions[ticker]
            self._cash += qty * price

        result = OrderResult(
            order_id=order_id,
            ticker=ticker,
            side=side,
            qty=qty,
            requested_price=limit_price,
            status="filled",
            submitted_at=datetime.now(tz=UTC).isoformat(),
            broker=self.name,
        )
        self.order_log.append(result)
        log.info("mock_order_filled", order_id=order_id, ticker=ticker, side=side, qty=qty)
        return result

    def get_positions(self) -> list[Position]:
        return list(self._positions.values())

    def get_account(self) -> AccountSummary:
        portfolio = self._cash + sum(p.market_value for p in self._positions.values())
        return AccountSummary(
            cash=self._cash,
            portfolio_value=portfolio,
            buying_power=self._cash,
        )

    def cancel_all(self) -> None:
        log.info("mock_cancel_all")


class AlpacaBroker(BaseBroker):
    """Alpaca paper / live trading broker.

    SAFETY: live mode requires:
      1. `BROKER_MODE=live` env (default `paper`)
      2. Explicit `confirm_live=True` constructor arg
      3. Non-empty alpaca credentials

    Otherwise we hard-fail at construction time.
    """

    name = "alpaca"

    def __init__(self, *, confirm_live: bool = False) -> None:
        from newsalpha.core.config import get_settings

        s = get_settings()
        mode = s.broker_mode
        if mode == "live" and not confirm_live:
            raise RuntimeError(
                "AlpacaBroker live mode requires confirm_live=True. "
                "Refusing to construct. Use paper mode or pass confirm_live."
            )

        api_key = s.alpaca_api_key.get_secret_value() if s.alpaca_api_key else ""
        secret = s.alpaca_secret_key.get_secret_value() if s.alpaca_secret_key else ""
        if not api_key or not secret:
            raise RuntimeError(
                "Alpaca credentials missing. Set ALPACA_API_KEY and ALPACA_SECRET_KEY."
            )

        from alpaca.trading.client import TradingClient
        self._client = TradingClient(
            api_key=api_key,
            secret_key=secret,
            paper=(mode == "paper"),
        )
        self._mode = mode
        log.info("alpaca_broker_init", mode=mode)

    def submit_order(
        self,
        ticker: str,
        qty: float,
        side: str,
        *,
        order_type: str = "market",
        limit_price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> OrderResult:
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest

        alpaca_side = OrderSide.BUY if side == "buy" else OrderSide.SELL

        try:
            if order_type == "limit" and limit_price:
                req = LimitOrderRequest(
                    symbol=ticker, qty=qty, side=alpaca_side,
                    time_in_force=TimeInForce.DAY, limit_price=limit_price,
                )
            else:
                req = MarketOrderRequest(
                    symbol=ticker, qty=qty, side=alpaca_side,
                    time_in_force=TimeInForce.DAY,
                )
            order = self._client.submit_order(req)
            return OrderResult(
                order_id=str(order.id),
                ticker=ticker, side=side, qty=qty,
                requested_price=limit_price,
                status=str(order.status).lower(),
                submitted_at=str(order.submitted_at),
                broker=self.name,
                raw={"client_order_id": getattr(order, "client_order_id", "")},
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("alpaca_submit_failed", ticker=ticker, side=side)
            return OrderResult(
                order_id="", ticker=ticker, side=side, qty=qty,
                requested_price=limit_price, status="rejected",
                submitted_at=datetime.now(tz=UTC).isoformat(),
                broker=self.name, error=str(exc),
            )

    def get_positions(self) -> list[Position]:
        try:
            positions = self._client.get_all_positions()
        except Exception as exc:  # noqa: BLE001
            log.warning("alpaca_get_positions_failed", error=str(exc))
            return []

        out: list[Position] = []
        for p in positions:
            out.append(Position(
                ticker=p.symbol,
                qty=float(p.qty),
                avg_entry_price=float(p.avg_entry_price),
                market_value=float(p.market_value),
                unrealized_pnl=float(p.unrealized_pl),
                side=str(p.side).lower(),
            ))
        return out

    def get_account(self) -> AccountSummary:
        try:
            acc = self._client.get_account()
        except Exception as exc:  # noqa: BLE001
            log.warning("alpaca_get_account_failed", error=str(exc))
            return AccountSummary(cash=0.0, portfolio_value=0.0, buying_power=0.0)

        return AccountSummary(
            cash=float(acc.cash),
            portfolio_value=float(acc.portfolio_value),
            buying_power=float(acc.buying_power),
            daytrade_count=int(getattr(acc, "daytrade_count", 0) or 0),
        )

    def cancel_all(self) -> None:
        try:
            self._client.cancel_orders()
        except Exception as exc:  # noqa: BLE001
            log.warning("alpaca_cancel_all_failed", error=str(exc))


def get_default_broker() -> BaseBroker:
    """Factory: mock → alpaca paper → alpaca live (with confirmation).

    Env override: `NEWSALPHA_BROKER=mock` forces MockBroker.
    """
    if os.environ.get("NEWSALPHA_BROKER") == "mock":
        return MockBroker()

    from newsalpha.core.config import get_settings
    s = get_settings()

    api_key = s.alpaca_api_key.get_secret_value() if s.alpaca_api_key else ""
    if not api_key:
        log.warning("no_alpaca_credentials_using_mock")
        return MockBroker()

    return AlpacaBroker(confirm_live=False)
