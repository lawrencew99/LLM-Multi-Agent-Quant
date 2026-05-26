from __future__ import annotations

from operator import add
from typing import Annotated, Any, TypedDict

from pydantic import BaseModel


# ── Boundary data models (validated at API edges) ───────────────────────────────
class NewsItem(BaseModel):
    """Normalised news event emitted by NewsCollector."""

    event_id: str
    ticker: str
    headline: str
    summary: str
    source: str
    url: str = ""
    published_at: str  # ISO 8601
    category: str = "general"  # general | earnings | merger | macro | legal | product
    sentiment_hint: float | None = None


class MarketSnapshot(BaseModel):
    ticker: str
    as_of: str  # ISO 8601 — strictly ≤ state.as_of (no lookahead)
    price: float
    open: float
    high: float
    low: float
    prev_close: float
    volume: int
    vwap: float | None = None
    atr14: float | None = None


# ── LangGraph state (TypedDict for native reducer support) ──────────────────────
class TradingState(TypedDict, total=False):
    """Shared state flowing through the LangGraph nodes.

    Lists annotated with `add` are append-only across parallel branches.
    """

    # Trigger context
    trigger: dict[str, Any]
    ticker: str
    as_of: str

    # Raw data (populated by NewsCollector)
    news_items: list[dict[str, Any]]
    market_snapshot: dict[str, Any] | None
    macro_context: dict[str, Any]

    # Analyst reports (populated in parallel fan-out)
    sentiment_report: dict[str, Any] | None
    fundamental_report: dict[str, Any] | None
    technical_report: dict[str, Any] | None
    macro_report: dict[str, Any] | None

    # Debate (append-only across rounds)
    bull_arguments: Annotated[list[dict[str, Any]], add]
    bear_arguments: Annotated[list[dict[str, Any]], add]
    debate_round: int
    debate_mode: str
    judge_verdict: dict[str, Any] | None

    # Decision
    trade_signal: dict[str, Any] | None
    risk_decision: dict[str, Any] | None
    final_orders: list[dict[str, Any]]

    # Telemetry
    cost_usd: Annotated[float, add]
    latency_ms: int
    trace_id: str
    errors: Annotated[list[str], add]
