"""Decision graph visualization — Plotly Sankey + node-flow charts.

Renders the LangGraph agent topology with live data overlay:
  - Node throughput (how many decisions passed through each agent)
  - Decision flow (Sankey diagram of bias → conviction → accept/reject → execute)
  - Agent latency / cost per node
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

import plotly.graph_objects as go


def build_decision_sankey(snapshots: list[dict[str, Any]]) -> go.Figure:
    """Build a Sankey diagram of signal flow through the decision pipeline.

    Stages:
        Total → Bias (long/short/neutral) → Conviction (high/med/low)
              → Risk (accept/reject) → Execution (filled/skipped)
    """
    if not snapshots:
        return _empty_figure("No snapshots to visualize")

    nodes = [
        "All Signals",                   # 0
        "Bias: Long",                    # 1
        "Bias: Short",                   # 2
        "Bias: Neutral",                 # 3
        "Conviction: High (≥0.75)",      # 4
        "Conviction: Med (0.5-0.75)",    # 5
        "Conviction: Low (<0.5)",        # 6
        "Risk: Accept",                  # 7
        "Risk: Reject",                  # 8
        "Executed",                      # 9
        "Skipped",                       # 10
    ]
    node_colors = [
        "#1f77b4", "#2ca02c", "#d62728", "#7f7f7f",
        "#2ca02c", "#bcbd22", "#ff7f0e",
        "#17becf", "#d62728", "#2ca02c", "#7f7f7f",
    ]

    sources: list[int] = []
    targets: list[int] = []
    values: list[int] = []

    counts: dict[str, int] = Counter()

    for s in snapshots:
        state = s.get("_state") or s.get("state") or {}
        verdict = state.get("judge_verdict") or {}
        risk = state.get("risk_decision") or {}

        bias = verdict.get("directional_bias", "neutral")
        conv = float(verdict.get("conviction") or 0)
        accepted = bool(risk.get("accepted", False))

        bias_node = {"long": 1, "short": 2}.get(bias, 3)
        if conv >= 0.75:
            conv_node = 4
        elif conv >= 0.5:
            conv_node = 5
        else:
            conv_node = 6

        risk_node = 7 if accepted else 8
        exec_node = 9 if accepted else 10

        counts[(0, bias_node)] += 1
        counts[(bias_node, conv_node)] += 1
        counts[(conv_node, risk_node)] += 1
        counts[(risk_node, exec_node)] += 1

    for (src, tgt), val in counts.items():
        sources.append(src)
        targets.append(tgt)
        values.append(val)

    fig = go.Figure(go.Sankey(
        node=dict(
            pad=15,
            thickness=20,
            line=dict(color="black", width=0.5),
            label=nodes,
            color=node_colors,
        ),
        link=dict(source=sources, target=targets, value=values),
    ))
    fig.update_layout(
        title_text=f"Decision Flow — {len(snapshots)} snapshots",
        font_size=11,
        height=500,
    )
    return fig


def build_agent_throughput_bar(snapshots: list[dict[str, Any]]) -> go.Figure:
    """Bar chart of how many snapshots reached each agent / pipeline stage."""
    if not snapshots:
        return _empty_figure("No snapshots")

    stage_keys: list[tuple[str, str]] = [
        ("News Collector", "news_items"),
        ("Sentiment", "sentiment_report"),
        ("Fundamental", "fundamental_report"),
        ("Technical", "technical_report"),
        ("Macro", "macro_report"),
        ("Bull Researcher", "bull_arguments"),
        ("Bear Researcher", "bear_arguments"),
        ("Debate Judge", "judge_verdict"),
        ("Trader", "trade_signal"),
        ("Risk Manager", "risk_decision"),
        ("Portfolio Manager", "portfolio_decision"),
    ]

    counts = []
    for _, key in stage_keys:
        n = sum(
            1 for s in snapshots
            if (s.get("_state") or s.get("state") or {}).get(key)
        )
        counts.append(n)

    fig = go.Figure(go.Bar(
        x=[name for name, _ in stage_keys],
        y=counts,
        marker_color="#1f77b4",
        text=counts,
        textposition="outside",
    ))
    fig.update_layout(
        title="Signals Reaching Each Agent",
        xaxis_title="Agent",
        yaxis_title="# Snapshots",
        height=400,
        xaxis_tickangle=-30,
    )
    return fig


def build_conviction_distribution(snapshots: list[dict[str, Any]]) -> go.Figure:
    """Histogram of conviction values across snapshots."""
    if not snapshots:
        return _empty_figure("No snapshots")

    convictions: list[float] = []
    accepted_convictions: list[float] = []
    for s in snapshots:
        state = s.get("_state") or s.get("state") or {}
        verdict = state.get("judge_verdict") or {}
        risk = state.get("risk_decision") or {}
        c = verdict.get("conviction")
        if c is None:
            continue
        convictions.append(float(c))
        if risk.get("accepted"):
            accepted_convictions.append(float(c))

    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=convictions, name="All", nbinsx=20,
        marker_color="#7f7f7f", opacity=0.6,
    ))
    fig.add_trace(go.Histogram(
        x=accepted_convictions, name="Accepted", nbinsx=20,
        marker_color="#2ca02c", opacity=0.8,
    ))
    fig.update_layout(
        title="Conviction Distribution (All vs Accepted)",
        xaxis_title="Conviction",
        yaxis_title="Count",
        barmode="overlay",
        height=400,
    )
    return fig


def build_regime_pie(snapshots: list[dict[str, Any]]) -> go.Figure:
    """Pie chart of decision count by macro regime."""
    if not snapshots:
        return _empty_figure("No snapshots")

    regime_counts: Counter[str] = Counter()
    for s in snapshots:
        state = s.get("_state") or s.get("state") or {}
        macro = state.get("macro_report") or {}
        regime_counts[macro.get("regime", "unknown")] += 1

    fig = go.Figure(go.Pie(
        labels=list(regime_counts.keys()),
        values=list(regime_counts.values()),
        hole=0.4,
        marker=dict(colors=["#2ca02c", "#d62728", "#ff7f0e", "#1f77b4", "#7f7f7f"]),
    ))
    fig.update_layout(title="Decisions by Macro Regime", height=400)
    return fig


def build_node_latency_box(snapshots: list[dict[str, Any]]) -> go.Figure:
    """Box plot of latency across nodes (if recorded in state)."""
    if not snapshots:
        return _empty_figure("No snapshots")

    latencies: dict[str, list[float]] = defaultdict(list)
    for s in snapshots:
        state = s.get("_state") or s.get("state") or {}
        node_lat = state.get("node_latencies") or {}
        for node, ms in node_lat.items():
            try:
                latencies[node].append(float(ms))
            except (TypeError, ValueError):
                continue

    if not latencies:
        return _empty_figure("No latency data recorded")

    fig = go.Figure()
    for node, vals in latencies.items():
        fig.add_trace(go.Box(y=vals, name=node, boxmean=True))
    fig.update_layout(
        title="Per-Node Latency Distribution (ms)",
        yaxis_title="Latency (ms)",
        height=400,
        showlegend=False,
    )
    return fig


def _empty_figure(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=message, xref="paper", yref="paper",
        x=0.5, y=0.5, showarrow=False, font=dict(size=14),
    )
    fig.update_layout(height=300, xaxis=dict(visible=False), yaxis=dict(visible=False))
    return fig
