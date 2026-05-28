"""Backtest engine built on backtrader.

Runs historical signal replay against actual OHLCV data, computing PnL,
drawdown, and per-trade attribution. Outputs results in a format compatible
with quantstats reporting.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

import backtrader as bt
import numpy as np
import pandas as pd

from newsalpha.data.connectors.market import get_default_market_connector
from newsalpha.utils.logging import get_logger

log = get_logger(__name__)

INITIAL_CASH = 100_000.0


class NewsAlphaStrategy(bt.Strategy):
    """Backtrader strategy that executes pre-computed signals.

    Signals are injected via `params.signals` — a list of dicts with keys:
        ticker, as_of (ISO), side, size_pct, entry_price, stop_loss, take_profit, conviction
    """

    params = (
        ("signals", []),
        ("max_position_pct", 0.05),
    )

    def __init__(self) -> None:
        self._pending_signals: list[dict[str, Any]] = list(self.params.signals)
        self._pending_signals.sort(key=lambda s: s.get("as_of", ""))
        self._active_trades: dict[str, dict[str, Any]] = {}
        self.trade_log: list[dict[str, Any]] = []

    def next(self) -> None:
        current_date = self.data.datetime.date(0)
        current_dt_str = current_date.isoformat()

        self._check_exits(current_date)

        while self._pending_signals and self._pending_signals[0].get("as_of", "")[:10] <= current_dt_str:
            sig = self._pending_signals.pop(0)
            self._execute_entry(sig, current_date)

    def _execute_entry(self, sig: dict[str, Any], date: Any) -> None:
        ticker = sig.get("ticker", "")
        side = sig.get("side", "")
        if side not in ("long", "short"):
            return

        size_pct = min(float(sig.get("size_pct", 0.03)), self.params.max_position_pct)
        portfolio_value = self.broker.getvalue()
        dollar_size = portfolio_value * size_pct
        price = self.data.close[0]
        if price <= 0:
            return

        shares = int(dollar_size / price)
        if shares <= 0:
            return

        if side == "long":
            self.buy(size=shares)
        else:
            self.sell(size=shares)

        self._active_trades[ticker] = {
            "side": side,
            "entry_price": price,
            "entry_date": date,
            "shares": shares,
            "stop_loss": float(sig.get("stop_loss", 0.0)),
            "take_profit": float(sig.get("take_profit", 0.0)),
            "conviction": sig.get("conviction", 0.0),
            "trace_id": sig.get("trace_id", ""),
        }

    def _check_exits(self, current_date: Any) -> None:
        to_close: list[str] = []
        price = self.data.close[0]

        for ticker, trade in self._active_trades.items():
            should_exit = False
            exit_reason = ""

            if trade["side"] == "long":
                if trade["stop_loss"] > 0 and price <= trade["stop_loss"]:
                    should_exit = True
                    exit_reason = "stop_loss_hit"
                elif trade["take_profit"] > 0 and price >= trade["take_profit"]:
                    should_exit = True
                    exit_reason = "take_profit_hit"
            else:
                if trade["stop_loss"] > 0 and price >= trade["stop_loss"]:
                    should_exit = True
                    exit_reason = "stop_loss_hit"
                elif trade["take_profit"] > 0 and price <= trade["take_profit"]:
                    should_exit = True
                    exit_reason = "take_profit_hit"

            if should_exit:
                shares = trade["shares"]
                if trade["side"] == "long":
                    self.sell(size=shares)
                else:
                    self.buy(size=shares)

                pnl_pct = (price / trade["entry_price"] - 1) * (1 if trade["side"] == "long" else -1)
                self.trade_log.append({
                    "ticker": ticker,
                    "side": trade["side"],
                    "entry_date": str(trade["entry_date"]),
                    "exit_date": str(current_date),
                    "entry_price": trade["entry_price"],
                    "exit_price": price,
                    "pnl_pct": pnl_pct,
                    "exit_reason": exit_reason,
                    "conviction": trade["conviction"],
                    "trace_id": trade["trace_id"],
                })
                to_close.append(ticker)

        for t in to_close:
            del self._active_trades[t]

    def stop(self) -> None:
        price = self.data.close[0]
        current_date = self.data.datetime.date(0)
        for ticker, trade in self._active_trades.items():
            pnl_pct = (price / trade["entry_price"] - 1) * (1 if trade["side"] == "long" else -1)
            self.trade_log.append({
                "ticker": ticker,
                "side": trade["side"],
                "entry_date": str(trade["entry_date"]),
                "exit_date": str(current_date),
                "entry_price": trade["entry_price"],
                "exit_price": price,
                "pnl_pct": pnl_pct,
                "exit_reason": "end_of_backtest",
                "conviction": trade["conviction"],
                "trace_id": trade["trace_id"],
            })


def run_backtest(
    ticker: str,
    signals: list[dict[str, Any]],
    *,
    start_date: str = "2023-01-01",
    end_date: str = "2023-12-31",
    initial_cash: float = INITIAL_CASH,
) -> dict[str, Any]:
    """Run a backtrader backtest for one ticker with pre-computed signals.

    Returns dict with:
      - portfolio_values: pd.Series of daily portfolio value
      - trade_log: list of executed trades
      - final_value: float
      - total_return_pct: float
      - n_trades: int
    """
    market = get_default_market_connector()
    bars = market.history(ticker, as_of_iso=end_date, lookback_days=500)

    if bars.empty:
        log.warning("backtest_no_data", ticker=ticker)
        return {"error": f"No data for {ticker}", "portfolio_values": pd.Series(dtype=float)}

    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date)
    bars = bars[(bars.index >= start_ts) & (bars.index <= end_ts)]

    if len(bars) < 5:
        log.warning("backtest_insufficient_data", ticker=ticker, n_bars=len(bars))
        return {"error": f"Insufficient data for {ticker}", "portfolio_values": pd.Series(dtype=float)}

    cerebro = bt.Cerebro()
    cerebro.broker.setcash(initial_cash)
    cerebro.broker.setcommission(commission=0.001)

    data_feed = bt.feeds.PandasData(
        dataname=bars,
        datetime=None,
        open="open",
        high="high",
        low="low",
        close="close",
        volume="volume",
        openinterest=-1,
    )
    cerebro.adddata(data_feed)

    ticker_signals = [s for s in signals if s.get("ticker") == ticker]
    cerebro.addstrategy(NewsAlphaStrategy, signals=ticker_signals)

    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name="time_return", timeframe=bt.TimeFrame.Days)

    strategies = cerebro.run()
    strat = strategies[0]

    time_returns = strat.analyzers.time_return.get_analysis()
    dates = sorted(time_returns.keys())
    returns_series = pd.Series(
        [time_returns[d] for d in dates],
        index=pd.DatetimeIndex(dates),
        name=ticker,
    )

    portfolio_values = (1 + returns_series).cumprod() * initial_cash

    final_value = cerebro.broker.getvalue()
    total_return = (final_value / initial_cash - 1) * 100

    log.info(
        "backtest_complete",
        ticker=ticker,
        final_value=round(final_value, 2),
        total_return_pct=round(total_return, 2),
        n_trades=len(strat.trade_log),
    )

    return {
        "ticker": ticker,
        "portfolio_values": portfolio_values,
        "returns": returns_series,
        "trade_log": strat.trade_log,
        "final_value": final_value,
        "total_return_pct": total_return,
        "n_trades": len(strat.trade_log),
        "initial_cash": initial_cash,
        "start_date": start_date,
        "end_date": end_date,
    }


def run_multi_ticker_backtest(
    tickers: list[str],
    signals: list[dict[str, Any]],
    *,
    start_date: str = "2023-01-01",
    end_date: str = "2023-12-31",
    initial_cash: float = INITIAL_CASH,
) -> dict[str, Any]:
    """Run backtests for multiple tickers and aggregate results.

    Returns combined portfolio returns, per-ticker breakdown, and aggregate metrics.
    """
    results: dict[str, Any] = {}
    all_returns: list[pd.Series] = []

    for ticker in tickers:
        result = run_backtest(
            ticker, signals,
            start_date=start_date,
            end_date=end_date,
            initial_cash=initial_cash / len(tickers),
        )
        results[ticker] = result
        if not result.get("returns", pd.Series(dtype=float)).empty:
            all_returns.append(result["returns"])

    if all_returns:
        combined_returns = pd.concat(all_returns, axis=1).mean(axis=1)
        combined_returns.name = "portfolio"
    else:
        combined_returns = pd.Series(dtype=float, name="portfolio")

    total_trades = sum(r.get("n_trades", 0) for r in results.values())
    all_trade_logs = []
    for r in results.values():
        all_trade_logs.extend(r.get("trade_log", []))

    return {
        "combined_returns": combined_returns,
        "per_ticker": results,
        "total_trades": total_trades,
        "all_trade_logs": all_trade_logs,
        "tickers": tickers,
        "start_date": start_date,
        "end_date": end_date,
    }
