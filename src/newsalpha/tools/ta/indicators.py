"""Vectorized TA indicators on close-price arrays.

Kept dependency-light (numpy + pandas only) — no `ta-lib` C extension —
so the project remains pure-Python installable on any platform.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period, min_periods=period).mean()
    loss = -delta.clip(upper=0).rolling(period, min_periods=period).mean()
    # If loss==0 across the window (pure uptrend), define RSI=100;
    # if gain==0 (pure downtrend), define RSI=0. Avoids div-by-zero NaNs.
    rs = gain / loss
    out = 100 - 100 / (1 + rs)
    out = out.where(loss != 0, 100.0)
    out = out.where(~((loss == 0) & (gain == 0)), 50.0)
    out = out.where(gain != 0, other=out.where(loss != 0, 100.0))
    return out.clip(0, 100)


def ema(close: pd.Series, period: int) -> pd.Series:
    return close.ewm(span=period, adjust=False).mean()


def macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def atr(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    typical = (high + low + close) / 3
    cum_vol = volume.cumsum().replace(0, np.nan)
    return (typical * volume).cumsum() / cum_vol


def support_resistance(close: pd.Series, lookback: int = 60) -> tuple[float, float]:
    """Naive S/R: rolling-window 25th and 75th percentile of recent closes.

    Good enough as one input among many for an LLM analyst — not a serious
    pivot-point implementation.
    """
    window = close.tail(lookback).dropna()
    if window.empty:
        return float("nan"), float("nan")
    return float(window.quantile(0.25)), float(window.quantile(0.75))


def summarize(bars: pd.DataFrame) -> dict[str, float | None]:
    """Compute the panel of indicators a TechnicalAnalyst sees per request.

    `bars` must have columns: open, high, low, close, volume; daily or 1h.
    Returns Python floats for trivially-JSON-serialisable agent input.
    """
    if bars.empty or len(bars) < 30:
        return {
            "price": None,
            "rsi14": None,
            "macd_hist": None,
            "atr14": None,
            "vwap": None,
            "support": None,
            "resistance": None,
            "trend_20": None,
            "n_bars": int(len(bars)),
        }

    close = bars["close"]
    macd_line, _, hist = macd(close)
    atr14 = atr(bars["high"], bars["low"], close)
    rsi14 = rsi(close)
    vwap_series = vwap(bars["high"], bars["low"], close, bars["volume"])
    support, resistance = support_resistance(close)
    trend_20 = (close.iloc[-1] / close.iloc[-20] - 1) if len(close) >= 20 else None

    def last(s: pd.Series) -> float | None:
        v = s.iloc[-1]
        return None if pd.isna(v) else float(v)

    return {
        "price": last(close),
        "rsi14": last(rsi14),
        "macd_hist": last(hist),
        "atr14": last(atr14),
        "vwap": last(vwap_series),
        "support": None if pd.isna(support) else float(support),
        "resistance": None if pd.isna(resistance) else float(resistance),
        "trend_20": float(trend_20) if trend_20 is not None and not pd.isna(trend_20) else None,
        "n_bars": int(len(bars)),
    }
