"""W6 tests for decision graph visualization (Plotly figures)."""

from __future__ import annotations

import plotly.graph_objects as go

from newsalpha.dashboard.decision_graph import (
    build_agent_throughput_bar,
    build_conviction_distribution,
    build_decision_sankey,
    build_node_latency_box,
    build_regime_pie,
)


def _mk_snap(bias: str, conviction: float, accepted: bool, regime: str = "bull") -> dict:
    return {
        "_state": {
            "judge_verdict": {"directional_bias": bias, "conviction": conviction},
            "risk_decision": {"accepted": accepted},
            "macro_report": {"regime": regime},
            "news_items": [{"id": "n1"}],
            "sentiment_report": {"polarity": 0.5},
            "fundamental_report": {"scores": {}},
            "technical_report": {"trend": "up"},
            "bull_arguments": [{"claims": []}],
            "bear_arguments": [{"claims": []}],
            "trade_signal": {"action": "buy"},
            "portfolio_decision": {"audit": []},
        }
    }


def test_sankey_handles_empty_snapshots() -> None:
    fig = build_decision_sankey([])
    assert isinstance(fig, go.Figure)


def test_sankey_with_real_snapshots() -> None:
    snaps = [
        _mk_snap("long", 0.8, True),
        _mk_snap("long", 0.7, True),
        _mk_snap("short", 0.6, False),
        _mk_snap("neutral", 0.4, False),
    ]
    fig = build_decision_sankey(snaps)
    assert isinstance(fig, go.Figure)
    sankey = fig.data[0]
    # All flows should sum to 4 paths × 4 stages = 16 link entries when distinct
    assert len(sankey.link.source) > 0
    assert sum(sankey.link.value) > 0


def test_throughput_bar_counts_correctly() -> None:
    snaps = [_mk_snap("long", 0.8, True) for _ in range(3)]
    fig = build_agent_throughput_bar(snaps)
    bar = fig.data[0]
    # Every snapshot has every key set, so counts should all be 3
    assert all(c == 3 for c in bar.y)


def test_throughput_bar_partial_pipeline() -> None:
    """A snapshot missing later-stage keys should show diminishing counts."""
    early = {"_state": {"news_items": [{"id": "n1"}], "sentiment_report": {}}}
    full = _mk_snap("long", 0.8, True)
    fig = build_agent_throughput_bar([early, full])
    counts = list(fig.data[0].y)
    # News (idx 0) should be 2, but Portfolio Manager (last) should be 1
    assert counts[0] == 2
    assert counts[-1] == 1


def test_conviction_distribution_separates_accepted() -> None:
    snaps = [
        _mk_snap("long", 0.9, True),
        _mk_snap("long", 0.85, True),
        _mk_snap("short", 0.4, False),
    ]
    fig = build_conviction_distribution(snaps)
    assert len(fig.data) == 2
    # First trace = all (3 entries), second = accepted (2 entries)
    assert len(fig.data[0].x) == 3
    assert len(fig.data[1].x) == 2


def test_regime_pie_counts_regimes() -> None:
    snaps = [
        _mk_snap("long", 0.8, True, regime="bull"),
        _mk_snap("long", 0.7, True, regime="bull"),
        _mk_snap("short", 0.6, False, regime="bear"),
    ]
    fig = build_regime_pie(snaps)
    pie = fig.data[0]
    label_to_val = dict(zip(pie.labels, pie.values, strict=True))
    assert label_to_val["bull"] == 2
    assert label_to_val["bear"] == 1


def test_latency_box_handles_no_data() -> None:
    snaps = [_mk_snap("long", 0.8, True)]
    fig = build_node_latency_box(snaps)
    assert isinstance(fig, go.Figure)


def test_latency_box_with_data() -> None:
    snap = _mk_snap("long", 0.8, True)
    snap["_state"]["node_latencies"] = {"trader": 100, "judge": 200}
    fig = build_node_latency_box([snap, snap])
    assert len(fig.data) == 2  # one box per node


def test_empty_inputs_return_figures_not_none() -> None:
    for fn in (build_decision_sankey, build_agent_throughput_bar,
               build_conviction_distribution, build_regime_pie,
               build_node_latency_box):
        fig = fn([])
        assert isinstance(fig, go.Figure)
