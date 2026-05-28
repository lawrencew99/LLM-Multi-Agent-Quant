# NewsAlpha

**English** · [简体中文](README.md)

> News-driven multi-agent US equity trading system · **v1.0**

A **LangGraph**-orchestrated system of 12 Anthropic Claude agents (Opus 4.7 for decisions / Sonnet 4.6 for analysis & debate / Haiku 4.5 for ingestion). News events trigger multi-round Bull/Bear debates, then flow through Trader → RiskManager → PortfolioManager, and finally execute via Alpaca paper trading. The full loop covers a backtest engine, decision replay, Reflection-based memory, and a real-time Streamlit dashboard.

## Project Status

| Phase | Theme | Status |
|---|---|---|
| W1 | Infrastructure + LangGraph skeleton | ✅ Done |
| W2 | Three-analyst parallel fan-out + TA toolkit | ✅ Done |
| W3 | Bull/Bear/Judge debate + Trader + RiskManager | ✅ Done |
| W4 | Backtest engine + Decision Replay + Reflection memory | ✅ Done |
| W5 | AlpacaBroker + MacroAnalyst + PortfolioManager + FastAPI + Dashboard | ✅ Done |
| W6 | Long backtest 2020-2025 + decision graph viz + v1.0 | ✅ Done |

**v1.0 scale**: 52+ Python modules / 19 test files / 123+ green tests / 12 closed-loop agents / 5 Streamlit pages / 4 backtest regime windows.
Full phase reports: [`docs/W1-W3_REPORT.md`](docs/W1-W3_REPORT.md) · [`docs/W4_REPORT.md`](docs/W4_REPORT.md) · [`docs/W5_REPORT.md`](docs/W5_REPORT.md) · [`docs/W6_REPORT.md`](docs/W6_REPORT.md)

## Three Differentiators

1. **A/B debate mechanism** — `adversarial / panel / socratic` modes are config-switchable; only [`configs/agents.yaml`](configs/agents.yaml) changes, the graph stays intact
2. **Decision-snapshot replay** — every graph run persists full state to JSON; Replay never re-invokes the LLM, only re-runs the deterministic risk rules; the Dashboard offers an A/B comparison UI
3. **Reflection memory** — after a position closes, rule-based / LLM reflections are written to a Qdrant vector store; the debate stage retrieves similar historical cases (embedding swap point ready)

## System Architecture

```
News WebHook / scheduled polling (Finnhub + Alpaca + SEC EDGAR)
         │
   NewsCollector (Haiku 4.5)
         │
   ┌─────┬─────┬─────┬─────┐
   ▼     ▼     ▼     ▼
Sentiment Fundamental Technical Macro    ← 4-way parallel fan-out
(Sonnet)  (Sonnet)    (Sonnet)  (Sonnet)
   └─────┴─────┴─────┴─────┘
         ▼
  BullResearcher ⇄ BearResearcher        ← multi-round debate (A/B configurable)
         │
    DebateJudge (Sonnet)
         │
   conviction < 0.6 → log_only → END
   conviction ≥ 0.6
         ▼
     Trader (Opus 4.7)
         ▼
   RiskManager (deterministic Python, no LLM)    ← trust boundary #1
         ▼
   PortfolioManager (regime × conviction × Kelly × vol, no LLM)  ← trust boundary #2
         │
   rejected → END        accepted → AlpacaBroker → Reflection memory
```

See [`src/newsalpha/core/graph.py`](src/newsalpha/core/graph.py) for the wiring.

## The 12 Agents

| # | Agent | Model | Role |
|---|---|---|---|
| 1 | NewsCollector | Haiku 4.5 | Fetch + summarize news |
| 2 | SentimentAnalyst | Sonnet 4.6 | polarity + confidence |
| 3 | FundamentalAnalyst | Sonnet 4.6 | growth/profit/cash/leverage 5-axis |
| 4 | TechnicalAnalyst | Sonnet 4.6 | TA indicator interpretation |
| 5 | MacroAnalyst | Sonnet 4.6 | regime classification + weighting |
| 6 | BullResearcher | Sonnet 4.6 | debate — bull side |
| 7 | BearResearcher | Sonnet 4.6 | debate — bear side |
| 8 | DebateJudge | Sonnet 4.6 | arbitration + conviction |
| 9 | Trader | Opus 4.7 | final order decision |
| 10 | RiskManager | (pure Python) | hard-rule gating |
| 11 | PortfolioManager | (pure Python) | regime-aware sizing |
| 12 | ReflectionAgent | Sonnet 4.6 | post-close lesson extraction |

## Quick Start

```bash
# 1. Install dependencies
uv sync --extra dev --extra ui --extra backtest

# 2. Start backend services (Postgres + Qdrant + Redis; optional)
make up

# 3. Configure secrets (only ANTHROPIC_API_KEY is required; mock mode works without keys)
cp .env.example .env

# 4. Run the hello-world demo
make demo

# 5. Run the test suite
make test            # all 123+ tests
NEWSALPHA_MOCK_DATA=1 make test   # offline mock

# 6. End-to-end backtest (synthetic-signal dry-run)
uv run python -m newsalpha.backtest.cli --synth

# 7. Long backtest 2020-2025 (4 regime windows)
NEWSALPHA_MOCK_DATA=1 uv run python -m newsalpha.backtest.long_backtest

# 8. Start the FastAPI service (REST + WebSocket)
uv run uvicorn newsalpha.api.app:app --reload

# 9. Start the Streamlit dashboard
uv run streamlit run src/newsalpha/dashboard/app.py
```

Without API keys, all tests and demos run offline on mock data — `NEWSALPHA_MOCK_DATA=1` + `NEWSALPHA_MEMORY_BACKEND=memory` + `NEWSALPHA_BROKER=mock`.

## Key Design Decisions

| Decision | Rationale |
|---|---|
| **TypedDict + `Annotated[..., add]` state** | LangGraph-native reducer; merges parallel fan-out writes from multiple agents |
| **Numbers in Python, narrative in LLMs** | TA indicators / risk rules / sizing are fully deterministic; LLMs explain, never compute |
| **Debate modes A/B-switched via prompt + config** | Reuses one LangGraph topology to study different debate mechanisms |
| **Trader short-circuits to hold on low conviction** | Skips Opus calls on weak signals — saves tokens + aligns with "miss rather than misfire" |
| **RiskManager / PortfolioManager never call LLMs** | Trust boundary between LLM judgment and real money; hard rules are auditable and replayable |
| **Every decision persists full state** | The snapshot is the source of truth — sole input for replay / postmortem / Reflection |
| **Replay never re-invokes the LLM** | Re-runs only `risk.rules.evaluate_signal` and `portfolio_manager` (pure Python) |
| **Live mode requires `confirm_live=True` + `BROKER_MODE=live`** | Paper by default; live trading needs both switches flipped |

## Risk Rules ([`configs/risk.yaml`](configs/risk.yaml))

| Rule | Threshold |
|---|---|
| Per-symbol position | ≤ 5% NAV |
| Per-sector position | ≤ 25% NAV |
| Mandatory stop-loss | back-fill at 2×ATR(14) when missing |
| Liquidity gate | avg daily turnover > $10M |
| Max leverage | 1.0 (MVP, no leverage) |
| Earnings blacklist | no new entries 24h before earnings |
| LLM exception | JSON parse fail → skip ticker for the day |
| Drawdown circuit | -10% from peak → flatten all + pause 24h |
| LLM daily budget | $20.0 / day (configurable; tripped on overrun) |

## Sizing Pipeline ([`src/newsalpha/execution/sizing.py`](src/newsalpha/execution/sizing.py))

```
base_size_pct (from Trader)
    │
    ├── × regime_weight       (from MacroAnalyst: crisis 0.3 / bear 0.6 / chop 0.75 / bull 1.0)
    ├── × conviction_factor   (Judge conviction; <0.6 zeros it out)
    ├── × kelly_factor        (fractional Kelly @ 0.25)
    ├── × vol_factor          (target vol 0.15, clipped to [0.25, 1.5]×)
    │
    ▼
final_size = min(..., max_single_pct=0.05)   ← every step audited into audit[]
```

## Directory Layout

```
newsalpha/
├── configs/
│   ├── agents.yaml              # per-agent model routing + debate mode
│   ├── risk.yaml                # risk thresholds
│   ├── universe.yaml            # ticker universe
│   └── prompts/system/          # markdown system prompts for the 12 agents
├── src/newsalpha/
│   ├── core/                    # state / graph / config
│   ├── agents/                  # the 12 agent nodes
│   ├── llm/                     # client / routing / budget
│   ├── tools/ta/                # pure-Python technical indicators
│   ├── data/connectors/         # finnhub / yfinance / mock
│   ├── risk/                    # deterministic hard rules
│   ├── execution/               # broker (Mock/Alpaca) + sizing
│   ├── backtest/                # backtrader engine + replay + long_backtest
│   ├── memory/                  # Qdrant + InMemory episode store
│   ├── api/                     # FastAPI + WebSocket
│   └── dashboard/               # Streamlit + Plotly decision graph
├── tests/unit/                  # 19 test files, 123+ tests
└── docs/                        # W1-W6 phase reports
```

## Tech Stack

- **Framework** — LangGraph · Anthropic SDK · pydantic-settings · structlog · tenacity
- **Data** — yfinance · Finnhub · Alpaca · FRED · Mock connectors
- **Storage** — Postgres · Qdrant · DuckDB+Parquet · Redis Streams · InMemory fallback
- **Backtest** — backtrader · quantstats (HTML reports)
- **API** — FastAPI · WebSocket
- **Frontend** — Streamlit · Plotly (Sankey + Bar + Pie + Histogram + Box)
- **Tooling** — uv · ruff · mypy · pytest · pre-commit

## Disclaimer

This system is for **research / demonstration purposes**. No signal or backtest result constitutes investment advice. US equity trading carries significant risk; users assume all consequences.

- Runs on Alpaca **paper trading** by default (`BROKER_MODE=paper`)
- Live mode requires both `BROKER_MODE=live` and `AlpacaBroker(confirm_live=True)`
- Raw Benzinga / Finnhub news text is not redistributed — only summaries and `event_id` are stored
