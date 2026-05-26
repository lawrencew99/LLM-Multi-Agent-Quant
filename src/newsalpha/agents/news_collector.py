from __future__ import annotations

from typing import Any

from newsalpha.core.state import TradingState
from newsalpha.data.connectors.market import get_default_market_connector
from newsalpha.data.connectors.news import get_default_news_connector
from newsalpha.utils.logging import get_logger

log = get_logger(__name__)

_news = get_default_news_connector()
_market = get_default_market_connector()


def news_collector(state: TradingState) -> dict[str, Any]:
    """W1 stub: fan-in news + market snapshot for `state.ticker` as of `state.as_of`.

    Real LLM-driven categorization arrives in W2 (this currently relies on the
    connector's own category hint).
    """
    ticker = state["ticker"]
    as_of = state.get("as_of", "")
    since = state.get("trigger", {}).get("since", "")

    items = _news.fetch(ticker, since_iso=since, until_iso=as_of)
    snap = _market.snapshot(ticker, as_of_iso=as_of)

    log.info(
        "news_collector_emitted",
        ticker=ticker,
        as_of=as_of,
        n_items=len(items),
        sources=sorted({i.source for i in items}),
    )

    return {
        "news_items": [i.model_dump() for i in items],
        "market_snapshot": snap.model_dump(),
    }
