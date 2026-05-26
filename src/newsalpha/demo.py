"""Hello-world demo — runs the W1 graph end-to-end.

Usage:
    uv run python -m newsalpha.demo
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

from rich import print as rprint
from rich.panel import Panel

from newsalpha.core.graph import build_graph
from newsalpha.core.state import TradingState
from newsalpha.utils.logging import configure_logging


def run(ticker: str = "AAPL") -> dict:
    configure_logging()
    graph = build_graph()

    initial: TradingState = {
        "trigger": {"type": "manual_demo", "since": ""},
        "ticker": ticker,
        "as_of": datetime.now(tz=UTC).isoformat(),
        "trace_id": f"demo-{datetime.now(tz=UTC).strftime('%Y%m%d%H%M%S')}",
        "debate_round": 0,
        "debate_mode": "adversarial",
        "cost_usd": 0.0,
        "latency_ms": 0,
        "bull_arguments": [],
        "bear_arguments": [],
        "final_orders": [],
        "errors": [],
    }
    return graph.invoke(initial)


def main() -> int:
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    out = run(ticker)
    rprint(
        Panel(
            json.dumps(out, indent=2, default=str),
            title=f"NewsAlpha demo — final state for {ticker}",
            border_style="cyan",
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
