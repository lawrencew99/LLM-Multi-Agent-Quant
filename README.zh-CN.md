# LLM多智能体量化交易系统

**简体中文** · [English](README.md)

> 新闻舆情驱动的多智能体美股交易系统 · **v1.0**

基于 **LangGraph** 编排 12 个 Anthropic Claude 智能体（Opus 4.7 决策 / Sonnet 4.6 分析+辩论 / Haiku 4.5 采集），从新闻事件触发，经多轮 Bull/Bear 辩论后由 Trader → RiskManager → PortfolioManager 决策，通过 Alpaca paper trading 执行。完整闭环包含回测引擎、决策回放、Reflection 经验记忆，以及 Streamlit 实时仪表盘。

## 项目状态

| 阶段 | 主题 | 状态 |
|---|---|---|
| W1 | 基础设施 + LangGraph 骨架 | ✅ 完成 |
| W2 | 三分析师并行 fan-out + TA 工具层 | ✅ 完成 |
| W3 | Bull/Bear/Judge 辩论 + Trader + RiskManager | ✅ 完成 |
| W4 | 回测引擎 + 决策 Replay + Reflection 记忆 | ✅ 完成 |
| W5 | AlpacaBroker + MacroAnalyst + PortfolioManager + FastAPI + Dashboard | ✅ 完成 |
| W6 | 长回测 2020-2025 + 决策图谱可视化 + v1.0 | ✅ 完成 |

**v1.0 规模**：52+ 个 Python 模块 / 19 测试文件 / 123+ 个测试全绿 / 12 智能体闭合 / 5 个 Streamlit 页面 / 4 个回测 regime 段。
完整阶段报告：[`docs/W1-W3_REPORT.md`](docs/W1-W3_REPORT.md) · [`docs/W4_REPORT.md`](docs/W4_REPORT.md) · [`docs/W5_REPORT.md`](docs/W5_REPORT.md) · [`docs/W6_REPORT.md`](docs/W6_REPORT.md)

## 三大差异化亮点

1. **A/B 辩论机制** — `adversarial / panel / socratic` 三种模式可配置切换，仅改 [`configs/agents.yaml`](configs/agents.yaml) 不动图结构
2. **决策快照回放** — 每次图运行的全量 state 持久化为 JSON；Replay 不重调 LLM、只重跑确定性风控规则；Dashboard 提供 A/B 对比 UI
3. **Reflection 记忆** — 平仓后规则化 / LLM 反思写入 Qdrant 向量库，辩论时检索相似历史案例（embedding swap point 已就绪）

## 系统架构

```
新闻 WebHook / 定时轮询 (Finnhub + Alpaca + SEC EDGAR)
         │
   NewsCollector (Haiku 4.5)
         │
   ┌─────┬─────┬─────┬─────┐
   ▼     ▼     ▼     ▼
Sentiment Fundamental Technical Macro    ← 4 路并行 fan-out
(Sonnet)  (Sonnet)    (Sonnet)  (Sonnet)
   └─────┴─────┴─────┴─────┘
         ▼
  BullResearcher ⇄ BearResearcher        ← 多轮辩论（A/B 可配置）
         │
    DebateJudge (Sonnet)
         │
   conviction < 0.6 → log_only → END
   conviction ≥ 0.6
         ▼
     Trader (Opus 4.7)
         ▼
   RiskManager (确定性 Python，无 LLM)    ← 信任边界 #1
         ▼
   PortfolioManager (regime × conviction × Kelly × vol，无 LLM)  ← 信任边界 #2
         │
   rejected → END        accepted → AlpacaBroker → Reflection 记忆
```

详见 [`src/newsalpha/core/graph.py`](src/newsalpha/core/graph.py)。

## 12 智能体

| # | Agent | 模型 | 角色 |
|---|---|---|---|
| 1 | NewsCollector | Haiku 4.5 | 抓取 + 摘要新闻 |
| 2 | SentimentAnalyst | Sonnet 4.6 | polarity + confidence |
| 3 | FundamentalAnalyst | Sonnet 4.6 | growth/profit/cash/leverage 5 维 |
| 4 | TechnicalAnalyst | Sonnet 4.6 | TA 指标解读 |
| 5 | MacroAnalyst | Sonnet 4.6 | regime 分类 + 权重 |
| 6 | BullResearcher | Sonnet 4.6 | 多空辩论 — bull |
| 7 | BearResearcher | Sonnet 4.6 | 多空辩论 — bear |
| 8 | DebateJudge | Sonnet 4.6 | 仲裁 + conviction |
| 9 | Trader | Opus 4.7 | 最终下单决策 |
| 10 | RiskManager | (纯 Python) | 硬规则审核 |
| 11 | PortfolioManager | (纯 Python) | regime-aware sizing |
| 12 | ReflectionAgent | Sonnet 4.6 | 平仓后经验提炼 |

## 快速开始

```bash
# 1. 安装依赖
uv sync --extra dev --extra ui --extra backtest

# 2. 启动后端服务（Postgres + Qdrant + Redis；可选）
make up

# 3. 配置密钥（最少需要 ANTHROPIC_API_KEY；无密钥可走 mock 模式）
cp .env.example .env

# 4. 跑通 hello-world demo
make demo

# 5. 运行测试套件
make test            # 全部 123+ 测试
NEWSALPHA_MOCK_DATA=1 make test   # 离线 mock

# 6. 端到端回测（合成信号 dry-run）
uv run python -m newsalpha.backtest.cli --synth

# 7. 长回测 2020-2025（4 个 regime 段）
NEWSALPHA_MOCK_DATA=1 uv run python -m newsalpha.backtest.long_backtest

# 8. 启动 FastAPI（REST + WebSocket）
uv run uvicorn newsalpha.api.app:app --reload

# 9. 启动 Streamlit Dashboard
uv run streamlit run src/newsalpha/dashboard/app.py
```

无 API key 时，全部测试与 demo 可在 Mock 数据下离线运行 —— `NEWSALPHA_MOCK_DATA=1` + `NEWSALPHA_MEMORY_BACKEND=memory` + `NEWSALPHA_BROKER=mock`。

## 关键设计决策

| 决策 | 理由 |
|---|---|
| **TypedDict + `Annotated[..., add]` 状态** | LangGraph 原生 reducer，并行 fan-out 合并多 agent 写入 |
| **数字算 Python，叙事算 LLM** | TA 指标 / 风控规则 / 仓位计算全确定性；LLM 只解释，不计算 |
| **辩论模式 A/B 通过 prompt + config 切换** | 复用同一 LangGraph 拓扑，研究不同辩论机制 |
| **Trader 在低 conviction 时短路 hold** | 弱信号下不发起 Opus 调用 — 省 token + 对齐"宁错过不错杀" |
| **RiskManager / PortfolioManager 永不调用 LLM** | LLM 判断与真金白银的信任边界；硬规则可审计可回放 |
| **每次决策落盘全量 state** | 快照即真相，是回放 / 复盘 / Reflection 的唯一数据源 |
| **Replay 不重新调 LLM** | 只重跑 `risk.rules.evaluate_signal` 与 `portfolio_manager`（纯 Python） |
| **Live mode 需 `confirm_live=True` + `BROKER_MODE=live`** | 默认 paper；实盘双重确认才能放行 |

## 风控规则（[`configs/risk.yaml`](configs/risk.yaml)）

| 规则 | 阈值 |
|---|---|
| 单票仓位 | ≤ 5% NAV |
| 单行业仓位 | ≤ 25% NAV |
| 强制止损 | 缺失时按 2×ATR(14) 回填 |
| 流动性门槛 | 日均成交额 > $10M |
| 最大杠杆 | 1.0（MVP 不加杠杆） |
| 财报黑名单 | 财报前 24h 不新开仓 |
| LLM 异常 | JSON 解析失败 → 当日跳过该 ticker |
| 回撤熔断 | 从峰值 -10% → 全平 + 暂停 24h |
| LLM 日预算 | $20.0 / day（可配置；超限熔断） |

## Sizing Pipeline（[`src/newsalpha/execution/sizing.py`](src/newsalpha/execution/sizing.py)）

```
base_size_pct (来自 Trader)
    │
    ├── × regime_weight       (来自 MacroAnalyst：crisis 0.3 / bear 0.6 / chop 0.75 / bull 1.0)
    ├── × conviction_factor   (Judge conviction，<0.6 直接零)
    ├── × kelly_factor        (fractional Kelly @ 0.25)
    ├── × vol_factor          (target vol 0.15，clip [0.25, 1.5]×)
    │
    ▼
final_size = min(..., max_single_pct=0.05)   ← 全程审计落 audit[]
```

## 目录结构

```
newsalpha/
├── configs/
│   ├── agents.yaml              # per-agent 模型路由 + 辩论模式
│   ├── risk.yaml                # 风控阈值
│   ├── universe.yaml            # 股票池
│   └── prompts/system/          # 12 个 agent 的 markdown 提示词
├── src/newsalpha/
│   ├── core/                    # state / graph / config
│   ├── agents/                  # 12 个 agent 节点
│   ├── llm/                     # client / routing / budget
│   ├── tools/ta/                # 纯 Python 技术指标
│   ├── data/connectors/         # finnhub / yfinance / mock
│   ├── risk/                    # 确定性硬规则
│   ├── execution/               # broker (Mock/Alpaca) + sizing
│   ├── backtest/                # backtrader engine + replay + long_backtest
│   ├── memory/                  # Qdrant + InMemory episode store
│   ├── api/                     # FastAPI + WebSocket
│   └── dashboard/               # Streamlit + Plotly 决策图谱
├── tests/unit/                  # 19 个测试文件，123+ tests
└── docs/                        # W1-W6 阶段报告
```

## 技术栈

- **框架** — LangGraph · Anthropic SDK · pydantic-settings · structlog · tenacity
- **数据** — yfinance · Finnhub · Alpaca · FRED · Mock connectors
- **存储** — Postgres · Qdrant · DuckDB+Parquet · Redis Streams · InMemory fallback
- **回测** — backtrader · quantstats（HTML 报告）
- **API** — FastAPI · WebSocket
- **前端** — Streamlit · Plotly（Sankey + Bar + Pie + Histogram + Box）
- **工具链** — uv · ruff · mypy · pytest · pre-commit

## 免责声明

本系统为**研究 / 演示用途**，所有信号与回测结果不构成投资建议。美股交易具有重大风险，使用者自担后果。

- 默认运行于 Alpaca **paper trading** 模式（`BROKER_MODE=paper`）
- 实盘模式需 `BROKER_MODE=live` + `AlpacaBroker(confirm_live=True)` 双重开关
- 不分发 Benzinga / Finnhub 原始新闻文本 — 仅保留摘要与 event_id
