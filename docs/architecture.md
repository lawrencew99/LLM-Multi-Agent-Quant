# NewsAlpha — Architecture Reference

## Overview

NewsAlpha is a news-driven multi-agent quantitative trading system for US equities. It uses LangGraph to orchestrate 12 Claude-based agents in a directed acyclic graph, with deterministic trust boundaries at the risk and portfolio management layers.

## System Layers

```
┌─────────────────────────────────────────────────────────────────────┐
│                         DATA INGESTION                               │
│  Finnhub (news) · yfinance (OHLCV) · Alpaca (streaming) · FRED     │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────────┐
│                     AGENT ORCHESTRATION (LangGraph)                   │
│                                                                       │
│  NewsCollector → [Sentiment | Fundamental | Technical | Macro]        │
│       → BullResearcher ⇄ BearResearcher → DebateJudge → Trader      │
│                                                                       │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────────┐
│                  TRUST BOUNDARY (Pure Python, no LLM)                 │
│                                                                       │
│  RiskManager (rules.py) → PortfolioManager (sizing.py)               │
│                                                                       │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────────┐
│                         EXECUTION                                     │
│  MockBroker (test/backtest) · AlpacaBroker (paper/live)              │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────────┐
│                     POST-TRADE                                        │
│  Decision Snapshots · ReflectionAgent → Qdrant episode memory        │
└─────────────────────────────────────────────────────────────────────┘
```

## Key Design Principles

1. **LLM generates text; Python computes numbers.** Every agent that produces a financial metric (TA indicators, risk thresholds, position sizing) uses deterministic Python code. LLMs only interpret and explain.

2. **Trust boundaries are explicit.** RiskManager and PortfolioManager sit between LLM-generated signals and the broker. They never call an LLM; they are auditable, replayable, and testable without API credentials.

3. **Snapshot-as-truth.** Every graph invocation writes the full TypedDict state to disk. This single artifact powers:
   - A/B replay (re-run risk/sizing with different params)
   - Backtest signal extraction
   - Debugging / auditing
   - Reflection agent (post-trade learning)

4. **Regime-aware everything.** MacroAnalyst classifies the market regime (bull/bear/chop/crisis). This regime weight flows into PortfolioManager's sizing, effectively downscaling positions during volatile periods without any LLM involvement.

## LangGraph State

The shared state is a `TypedDict` with `Annotated` fields using `operator.add` as reducer for parallel fan-out merge:

```python
class TradingState(TypedDict):
    # Input
    trigger: dict
    ticker: str
    as_of: str
    trace_id: str
    debate_round: int
    debate_mode: str

    # Accumulating (Annotated[..., add])
    cost_usd: float
    latency_ms: int
    errors: list[str]
    bull_arguments: list[dict]
    bear_arguments: list[dict]
    final_orders: list[dict]

    # Single-write
    news_items: list[dict] | None
    sentiment_report: dict | None
    fundamental_report: dict | None
    technical_report: dict | None
    macro_report: dict | None
    macro_context: dict | None
    judge_verdict: dict | None
    trade_signal: dict | None
    risk_decision: dict | None
    portfolio_decision: dict | None
    execution_results: list[dict]
```

## Model Routing

| Tier | Model | Use |
|---|---|---|
| Opus 4.7 | `claude-opus-4-7` | Trader (final decision — high stakes) |
| Sonnet 4.6 | `claude-sonnet-4-6` | Analysts, Bull/Bear, Judge, Macro, Reflection |
| Haiku 4.5 | `claude-haiku-4-5-20251001` | NewsCollector (high volume, low cost) |

Budget: `LLM_DAILY_BUDGET_USD=20.0` with circuit breaker. Each call logs cost to state.

## Debate Mechanism

Three configurable modes via `configs/agents.yaml`:

| Mode | Flow |
|---|---|
| `adversarial` | Bull → Bear (rebuts) → Judge (1 round) |
| `panel` | Bull → Bear → round 2 → ... → Judge |
| `socratic` | Bull → Bear → follow-up questions → Judge |

The graph topology is identical; only the prompts and round count differ.

## Backtest Pipeline

```
Snapshots (or synth signals) → extract_signals_for_backtest()
    → run_multi_ticker_backtest() [backtrader]
        → compute_all_metrics()
            → write_markdown_report() / generate_html_report()
```

Long backtest (2020–2025) splits into 4 regime segments:
- COVID crisis (2020-02 to 2020-06)
- Bull run (2021)
- Bear market (2022)
- Recovery (2023–2024)

## API Layer

- **FastAPI** — REST endpoints for snapshots, memory, replay, graph trigger
- **WebSocket** — `/ws/events` for real-time node execution streaming
- **Streamlit** — 6-page dashboard (Decisions, Decision Graph, Debate, Backtest, Memory, Replay)

## Directory Layout

```
src/newsalpha/
├── core/            # state.py, graph.py, config.py
├── agents/          # 12 agent node functions
├── llm/             # client.py, routing.py, budget.py
├── tools/ta/        # RSI, MACD, Bollinger, ATR, etc.
├── data/connectors/ # market.py, news.py (yfinance, finnhub, mock)
├── risk/            # rules.py (deterministic)
├── execution/       # broker.py, sizing.py
├── backtest/        # engine.py, replay.py, metrics.py, reports.py, long_backtest.py
├── memory/          # episodes.py (Qdrant + InMemory)
├── api/             # app.py (FastAPI + WS)
├── dashboard/       # app.py (Streamlit), decision_graph.py (Plotly)
└── utils/           # logging.py
```
