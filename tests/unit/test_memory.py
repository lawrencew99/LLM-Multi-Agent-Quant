"""Tests for W4: episode store + reflection batch."""

from __future__ import annotations

from newsalpha.agents.reflection import reflect_batch
from newsalpha.memory.episodes import (
    Episode,
    InMemoryEpisodeStore,
    embed_text,
    retrieve_similar,
    write_episode,
)


def test_embedding_deterministic() -> None:
    a = embed_text("hello AAPL bullish")
    b = embed_text("hello AAPL bullish")
    assert a == b


def test_embedding_different_texts_differ() -> None:
    a = embed_text("AAPL bullish")
    b = embed_text("TSLA bearish")
    assert a != b


def test_embedding_normalized() -> None:
    v = embed_text("test")
    norm = sum(x * x for x in v) ** 0.5
    assert abs(norm - 1.0) < 1e-6


def test_episode_to_payload_roundtrip() -> None:
    ep = Episode(
        ticker="AAPL", side="long",
        entry_date="2023-01-15", exit_date="2023-02-10",
        pnl_pct=0.05, conviction=0.75,
        regime="bull",
        what_worked=["RSI rising", "earnings beat"],
        lessons=["trust earnings momentum"],
        key_signals=["sentiment.polarity=0.8"],
        trace_id="abc123",
    )
    p = ep.to_payload()
    ep2 = Episode.from_payload(p)
    assert ep2.ticker == ep.ticker
    assert ep2.pnl_pct == ep.pnl_pct
    assert ep2.what_worked == ep.what_worked
    assert ep2.lessons == ep.lessons


def test_in_memory_store_upsert_and_search() -> None:
    store = InMemoryEpisodeStore()

    ep1 = Episode(ticker="AAPL", side="long", entry_date="2023-01-01",
                  exit_date="2023-01-15", pnl_pct=0.05, conviction=0.75,
                  regime="bull", lessons=["earnings momentum works"])
    ep2 = Episode(ticker="MSFT", side="long", entry_date="2023-02-01",
                  exit_date="2023-02-15", pnl_pct=-0.03, conviction=0.65,
                  regime="chop", lessons=["chop kills momentum"])

    write_episode(ep1, store=store)
    write_episode(ep2, store=store)
    assert store.count() == 2


def test_in_memory_store_ticker_filter() -> None:
    store = InMemoryEpisodeStore()

    for i, ticker in enumerate(["AAPL", "AAPL", "MSFT"]):
        ep = Episode(ticker=ticker, side="long", entry_date="2023-01-01",
                     exit_date="2023-02-01", pnl_pct=0.02, conviction=0.7,
                     regime="bull", trace_id=f"t{i}")
        write_episode(ep, store=store)

    aapl = retrieve_similar("test query", ticker="AAPL", limit=10, store=store)
    assert all(e.ticker == "AAPL" for e in aapl)
    assert len(aapl) == 2


def test_retrieve_similar_returns_at_most_limit() -> None:
    store = InMemoryEpisodeStore()
    for i in range(10):
        ep = Episode(ticker=f"T{i}", side="long", entry_date="2023-01-01",
                     exit_date="2023-02-01", pnl_pct=0.01, conviction=0.7,
                     regime="bull", trace_id=f"tid-{i}")
        write_episode(ep, store=store)

    results = retrieve_similar("query", limit=3, store=store)
    assert len(results) == 3


def test_reflect_batch_creates_episodes(monkeypatch) -> None:
    """Mock the default store with an in-memory one; verify episodes flow."""
    from newsalpha.memory import episodes as ep_module

    test_store = InMemoryEpisodeStore()
    monkeypatch.setattr(ep_module, "get_default_store", lambda: test_store)

    trade_log = [
        {"ticker": "AAPL", "side": "long", "entry_date": "2023-01-01",
         "exit_date": "2023-02-01", "pnl_pct": 0.08, "conviction": 0.8,
         "exit_reason": "take_profit_hit", "trace_id": "t1"},
        {"ticker": "MSFT", "side": "long", "entry_date": "2023-03-01",
         "exit_date": "2023-03-15", "pnl_pct": -0.04, "conviction": 0.65,
         "exit_reason": "stop_loss_hit", "trace_id": "t2"},
    ]

    episodes = reflect_batch(trade_log, regime="bull")
    assert len(episodes) == 2
    assert test_store.count() == 2
    assert episodes[0].what_worked
    assert episodes[1].what_failed
