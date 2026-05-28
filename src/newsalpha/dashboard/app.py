"""Streamlit dashboard for NewsAlpha.

Run:
    uv run streamlit run src/newsalpha/dashboard/app.py

Pages:
  - Decisions     — recent decision snapshots with conviction, bias, accept/reject
  - Backtest      — equity curve, metrics, trade log
  - Debate Viewer — bull vs bear arguments side-by-side for a snapshot
  - Memory        — recent reflection episodes
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from newsalpha.backtest.replay import replay_decision
from newsalpha.backtest.snapshots import list_snapshots, read_snapshot
from newsalpha.core.config import REPO_ROOT


def _load_snapshots() -> list[dict]:
    rows = []
    for p in list_snapshots():
        try:
            snap = read_snapshot(p)
            state = snap.get("state", {})
            verdict = state.get("judge_verdict") or {}
            risk = state.get("risk_decision") or {}
            rows.append({
                "snapshot_id": p.stem,
                "ticker": snap.get("ticker"),
                "as_of": snap.get("as_of"),
                "trace_id": snap.get("trace_id"),
                "bias": verdict.get("directional_bias"),
                "conviction": verdict.get("conviction"),
                "accepted": risk.get("accepted", False),
                "size_pct": risk.get("final_size_pct", 0),
                "reasons": ", ".join(risk.get("reasons", []))[:80],
                "_path": str(p),
                "_state": state,
            })
        except (json.JSONDecodeError, KeyError):
            continue
    return rows


def page_decisions() -> None:
    st.header("Recent Decisions")
    snaps = _load_snapshots()
    if not snaps:
        st.info("No snapshots yet. Run `make demo` or trigger a graph run.")
        return

    df = pd.DataFrame([{k: v for k, v in s.items() if not k.startswith("_")} for s in snaps])
    df = df.sort_values("as_of", ascending=False)

    col1, col2, col3 = st.columns(3)
    col1.metric("Total decisions", len(df))
    col2.metric("Accepted", int(df["accepted"].sum()))
    col3.metric("Avg conviction",
                f"{df['conviction'].dropna().astype(float).mean():.2f}" if not df.empty else "—")

    st.dataframe(df, use_container_width=True, height=400)

    st.subheader("Inspect a snapshot")
    selected = st.selectbox("Snapshot", df["snapshot_id"].tolist())
    if selected:
        snap = next(s for s in snaps if s["snapshot_id"] == selected)
        with st.expander("Full state JSON", expanded=False):
            st.json(snap["_state"])


def page_backtest() -> None:
    st.header("Backtest Reports")

    report_dir = REPO_ROOT / "data" / "reports"
    if not report_dir.exists():
        st.info("No reports yet. Run `python -m newsalpha.backtest.cli`.")
        return

    metric_files = sorted(report_dir.glob("metrics_*.json"))[-10:]
    if not metric_files:
        st.info("No metrics found.")
        return

    selected = st.selectbox("Report", [p.stem for p in metric_files][::-1])
    p = next(p for p in metric_files if p.stem == selected)
    metrics = json.loads(p.read_text(encoding="utf-8"))

    cols = st.columns(4)
    cols[0].metric("Total return %", f"{metrics.get('total_return_pct', 0):.2f}")
    cols[1].metric("Sharpe", f"{metrics.get('sharpe_ratio', 0):.2f}")
    cols[2].metric("Max DD %", f"{metrics.get('max_drawdown', 0)*100:.2f}")
    cols[3].metric("Win rate %", f"{metrics.get('win_rate', 0)*100:.1f}")

    cols2 = st.columns(4)
    cols2[0].metric("Sortino", f"{metrics.get('sortino_ratio', 0):.2f}")
    cols2[1].metric("Profit factor", f"{metrics.get('profit_factor', 0):.2f}")
    cols2[2].metric("CAGR %", f"{metrics.get('cagr', 0)*100:.2f}")
    cols2[3].metric("# trades", metrics.get('total_trades', 0))

    md_path = report_dir / f"backtest_{p.stem.split('_', 1)[1]}.md"
    if md_path.exists():
        with st.expander("Full markdown report"):
            st.markdown(md_path.read_text(encoding="utf-8"))


def page_debate() -> None:
    st.header("Debate Viewer")
    snaps = _load_snapshots()
    snaps_with_debate = [s for s in snaps if s["_state"].get("bull_arguments")
                         or s["_state"].get("bear_arguments")]
    if not snaps_with_debate:
        st.info("No debates recorded yet.")
        return

    snap_id = st.selectbox(
        "Snapshot",
        [f"{s['snapshot_id']} — {s['ticker']} ({s['bias']}/{s['conviction']})"
         for s in snaps_with_debate],
    )
    selected = snaps_with_debate[
        [f"{s['snapshot_id']} — {s['ticker']} ({s['bias']}/{s['conviction']})"
         for s in snaps_with_debate].index(snap_id)
    ]
    state = selected["_state"]

    bull = state.get("bull_arguments", [])
    bear = state.get("bear_arguments", [])
    verdict = state.get("judge_verdict") or {}

    st.subheader(f"Verdict: {verdict.get('directional_bias', '—')} @ "
                 f"conviction={verdict.get('conviction', 0):.2f}")
    st.write(verdict.get("rationale", ""))

    col_bull, col_bear = st.columns(2)
    with col_bull:
        st.markdown("### 🐂 Bull")
        for i, arg in enumerate(bull):
            with st.container():
                st.markdown(f"**Round {arg.get('round', '?')} · #{i}**")
                for c in arg.get("claims", []):
                    st.markdown(f"- {c.get('text', c) if isinstance(c, dict) else c}")
                st.caption(f"Conviction: {arg.get('conviction', '—')}")
    with col_bear:
        st.markdown("### 🐻 Bear")
        for i, arg in enumerate(bear):
            with st.container():
                st.markdown(f"**Round {arg.get('round', '?')} · #{i}**")
                for c in arg.get("claims", []):
                    st.markdown(f"- {c.get('text', c) if isinstance(c, dict) else c}")
                st.caption(f"Rebuts: {arg.get('rebuts_bull_id', '—')}")


def page_memory() -> None:
    st.header("Reflection Memory")

    os.environ.setdefault("NEWSALPHA_MEMORY_BACKEND", "memory")
    from newsalpha.memory.episodes import InMemoryEpisodeStore, get_default_store

    store = get_default_store()
    if isinstance(store, InMemoryEpisodeStore):
        items = store._items[-30:]
        if not items:
            st.info("No reflections recorded yet. Run a backtest with reflect_batch().")
            return

        rows = []
        for _, _, p in items:
            rows.append({
                "ticker": p.get("ticker"),
                "side": p.get("side"),
                "entry": p.get("entry_date"),
                "exit": p.get("exit_date"),
                "pnl_pct": p.get("pnl_pct"),
                "regime": p.get("regime"),
                "lessons": " | ".join(p.get("lessons", [])[:2]),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
    else:
        st.info("Connected to Qdrant. Browsing not implemented in W5 — use API.")


def page_replay() -> None:
    st.header("Replay with Risk Override")

    snaps = _load_snapshots()
    if not snaps:
        st.info("No snapshots to replay.")
        return

    snap_id = st.selectbox("Snapshot", [s["snapshot_id"] for s in snaps])
    selected = next(s for s in snaps if s["snapshot_id"] == snap_id)

    st.subheader("Override risk parameters")
    max_single = st.slider("Max single-ticker pct", 0.001, 0.10, 0.05, 0.005)
    atr_mult = st.slider("ATR stop multiplier", 1.0, 5.0, 2.0, 0.1)

    if st.button("Run replay"):
        override = {
            "position": {"max_single_pct": max_single},
            "stops": {"atr_multiplier": atr_mult},
            "universe_filter": {"min_avg_dollar_volume_usd": 0},
        }
        replayed = replay_decision(selected["_path"], override_risk_config=override)

        col_orig, col_replay = st.columns(2)
        with col_orig:
            st.markdown("### Original")
            st.json(selected["_state"].get("risk_decision", {}))
        with col_replay:
            st.markdown("### Replayed")
            st.json(replayed.get("risk_decision", {}))


def page_decision_graph() -> None:
    st.header("Decision Graph — Signal Flow Visualization")

    from newsalpha.dashboard.decision_graph import (
        build_agent_throughput_bar,
        build_conviction_distribution,
        build_decision_sankey,
        build_regime_pie,
    )

    snaps = _load_snapshots()
    if not snaps:
        st.info("No snapshots to visualize. Run `make demo` or trigger a graph run.")
        return

    st.subheader("Signal Flow (Sankey)")
    fig_sankey = build_decision_sankey(snaps)
    st.plotly_chart(fig_sankey, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Agent Throughput")
        fig_bar = build_agent_throughput_bar(snaps)
        st.plotly_chart(fig_bar, use_container_width=True)
    with col2:
        st.subheader("Macro Regime")
        fig_pie = build_regime_pie(snaps)
        st.plotly_chart(fig_pie, use_container_width=True)

    st.subheader("Conviction Distribution")
    fig_hist = build_conviction_distribution(snaps)
    st.plotly_chart(fig_hist, use_container_width=True)


def main() -> None:
    st.set_page_config(page_title="NewsAlpha Dashboard", page_icon="📈", layout="wide")
    st.title("NewsAlpha — Multi-Agent Trading Dashboard")
    st.caption("News-driven multi-agent quantitative system · "
               f"powered by LangGraph + Anthropic Claude")

    page = st.sidebar.radio(
        "Page",
        ["Decisions", "Decision Graph", "Debate Viewer", "Backtest", "Memory", "Replay (A/B)"],
    )

    if page == "Decisions":
        page_decisions()
    elif page == "Decision Graph":
        page_decision_graph()
    elif page == "Debate Viewer":
        page_debate()
    elif page == "Backtest":
        page_backtest()
    elif page == "Memory":
        page_memory()
    elif page == "Replay (A/B)":
        page_replay()


if __name__ == "__main__":
    main()
else:
    main()
