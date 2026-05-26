from __future__ import annotations

from datetime import UTC, datetime

from newsalpha.core.graph import build_graph
from newsalpha.core.state import TradingState


def test_w1_graph_runs_end_to_end() -> None:
    """The W1 graph must accept a minimal state and emit news + market snapshot."""
    graph = build_graph()
    initial: TradingState = {
        "trigger": {"type": "test", "since": ""},
        "ticker": "AAPL",
        "as_of": datetime.now(tz=UTC).isoformat(),
        "trace_id": "test-w1",
        "debate_round": 0,
        "debate_mode": "adversarial",
        "cost_usd": 0.0,
        "latency_ms": 0,
        "bull_arguments": [],
        "bear_arguments": [],
        "final_orders": [],
        "errors": [],
    }

    out = graph.invoke(initial)

    assert out["ticker"] == "AAPL"
    assert len(out["news_items"]) >= 1
    assert out["news_items"][0]["ticker"] == "AAPL"
    assert out["market_snapshot"]["ticker"] == "AAPL"
    assert out["market_snapshot"]["price"] > 0
