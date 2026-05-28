# NewsAlpha — 项目总报告 (v1.0)

> 新闻舆情驱动的多智能体美股交易系统
> 报告日期：2026-05-28
> 项目周期：6 周（W1 → W6 全部收官）
> 报告作者：项目主理人（个人 portfolio 项目）

---

## 摘要

NewsAlpha 是一个端到端的、以新闻事件触发为入口的多智能体量化交易研究系统。
它使用 LangGraph 编排 12 个基于 Anthropic Claude 的智能体（Opus 4.7 / Sonnet 4.6 / Haiku 4.5 三层路由），从新闻采集、四路并行分析、Bull/Bear 多轮辩论、Judge 仲裁，到 Trader 决策、确定性 RiskManager 审核、regime-aware PortfolioManager 调仓、Alpaca Broker 执行、Reflection 经验提炼，形成完整闭环。

整套系统设计的核心信条是：

- **LLM 算解释、Python 算数字**：所有金融指标（TA、风控规则、仓位计算）都跑在确定性 Python 代码里；LLM 只做叙事性判断与解释。
- **快照即真相**：每次决策的全量 state 写盘为 JSON；回放、复盘、回测、Reflection 全部以此为唯一数据源。
- **两道信任边界**：RiskManager 与 PortfolioManager 永不调用 LLM，纯 Python、可审计、可回放、可单测，是 LLM 信号与真金白银之间的最后两道闸门。
- **默认 paper、双开关 live**：实盘需要 `BROKER_MODE=live` **且** `AlpacaBroker(confirm_live=True)` —— 缺一不可。

**v1.0 累计交付**：

| 维度 | 数值 |
|---|---|
| Python 源码模块 | 54 个 |
| Python 源码行数 | 4,946 行 |
| 单元测试文件 | 19 个 |
| 单元测试数量 | **123 个全绿** |
| 单元测试行数 | 2,008 行 |
| Agent prompt 模板 | 9 份 markdown |
| YAML 配置 | 3 份 |
| 阶段报告文档 | 4 份（W1-W3 / W4 / W5 / W6） |
| 架构文档 | 1 份（architecture.md） |
| 智能体节点 | 12 个 |
| Streamlit 仪表盘页面 | 6 页 |
| 命令行入口 | 5 个（demo / backtest / long-backtest / api / dashboard） |
| 长回测 regime 段 | 4 段（COVID / Bull / Bear / Recovery） |

---

## 1. 项目背景与目标

### 1.1 立项动机

本项目是为量化投研岗位求职准备的 portfolio 项目，立项的三条硬目标：

1. **能跑** — 面试官 clone 仓库后，无 API key 即可在 mock 模式下一键跑通全部 123 个测试与端到端 demo。
2. **能讲** — 文档（README + architecture.md + 4 份阶段报告）+ 6 页 Streamlit dashboard 让评审者用 5 分钟掌握整套系统的设计动机与取舍。
3. **能审** — 每次决策落盘全量 state，任何风控/仓位结论都能精确定位到具体规则、具体行号、具体配置版本。

### 1.2 与市面常见 LLM 量化 demo 的差异化

| 维度 | 我们的做法 | 区别于多数 demo |
|---|---|---|
| **Agent 架构** | 12 个 LangGraph 节点，并行 fan-out + 多轮辩论 + 双信任边界 | ≠ 单 prompt + 工具调用循环 |
| **回测** | 决策快照 → 信号 → backtrader → quantstats；Replay 不重调 LLM | ≠ 直接喂历史价格让 LLM "假装" 决策 |
| **风控** | 100% 纯 Python 规则，可单测、可回放、可审计 | ≠ "让 LLM 评估风险" |
| **存储** | TypedDict 全量快照 + Qdrant episode 记忆 + 决策日志 | ≠ 只存 final order |
| **可视化** | 5 种 Plotly 图（Sankey/Bar/Pie/Histogram/Box）+ A/B Replay UI | ≠ 仅打印日志 |
| **安全** | paper 默认 + live 双重确认 + 日预算熔断 + 信任边界 | ≠ "demo 跑通就好" |
| **A/B 实验** | 辩论模式 `adversarial / panel / socratic` 仅改 YAML 切换 | ≠ 单一辩论模板 |

---

## 2. 系统架构

### 2.1 五层架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                         数据采集层                                    │
│  Finnhub (news) · yfinance (OHLCV) · Alpaca (streaming) · FRED      │
│                  +  Mock connectors（CI / 离线开发）                 │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────────┐
│                  智能体编排层（LangGraph）                            │
│                                                                       │
│  NewsCollector → [Sentiment | Fundamental | Technical | Macro]       │
│       → BullResearcher ⇄ BearResearcher → DebateJudge → Trader       │
│                                                                       │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────────┐
│                  信任边界层（纯 Python，零 LLM）                       │
│                                                                       │
│  RiskManager (rules.py) → PortfolioManager (sizing.py)               │
│                                                                       │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────────┐
│                         执行层                                        │
│  MockBroker (test/backtest) · AlpacaBroker (paper/live)              │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────────┐
│                       事后处理层                                       │
│  Decision Snapshots · ReflectionAgent → Qdrant episode memory        │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 LangGraph 拓扑（v1.0 最终版）

```
START
  │
  ▼
news_collector
  │ (fan-out)
  ├──→ sentiment_analyst   ┐
  ├──→ fundamental_analyst │  4 路并行
  ├──→ technical_analyst   │  写入不相交 state slot
  └──→ macro_analyst       ┘
  │ (fan-in via analysts_ready barrier)
  ▼
debate_orchestrator  ← 读 configs/agents.yaml 决定 debate mode + rounds
  │
  ▼
bull_researcher ─→ bear_researcher ─→ round_advancer
  ▲                                          │
  │   (next_round ≤ max_rounds → continue)   │
  └──────────────────────────────────────────┘
                                             │
                              (round > max → judge)
                                             ▼
                                       debate_judge
                                             │
                          ┌──────────────────┴──────────────┐
                conviction < 0.6                conviction ≥ 0.6
                bias == neutral                 bias != neutral
                          │                                 │
                          ▼                                 ▼
                      log_only                          trader (Opus 4.7)
                          │                                 │
                          ▼                                 ▼
                         END                          risk_manager (纯 Python)
                                                          │
                                                          ▼
                                                  portfolio_manager (纯 Python)
                                                          │
                                                          ▼
                                                         END
```

定义在 [src/newsalpha/core/graph.py](src/newsalpha/core/graph.py)。

### 2.3 状态契约：TradingState

定义在 [src/newsalpha/core/state.py](src/newsalpha/core/state.py)，是整个系统的"宪法"：

```python
class TradingState(TypedDict, total=False):
    # Trigger
    trigger: dict
    ticker: str
    as_of: str

    # Raw data
    news_items: list[dict]
    market_snapshot: dict | None
    macro_context: dict

    # Analyst reports（并行写入不相交 slot）
    sentiment_report: dict | None
    fundamental_report: dict | None
    technical_report: dict | None
    macro_report: dict | None

    # Debate（多轮 append-only）
    bull_arguments: Annotated[list[dict], add]
    bear_arguments: Annotated[list[dict], add]
    debate_round: int
    debate_mode: str
    judge_verdict: dict | None

    # Decision
    trade_signal: dict | None
    risk_decision: dict | None
    portfolio_decision: dict | None
    final_orders: list[dict]
    execution_results: list[dict]

    # Telemetry
    cost_usd: Annotated[float, add]       # 并行成本累加
    latency_ms: int
    trace_id: str
    errors: Annotated[list[str], add]
```

**关键设计决策**：

- 选 `TypedDict` 而非 Pydantic `BaseModel`：LangGraph 原生支持 `Annotated[..., add]` reducer，并行 fan-out 才能正确合并。
- `bull_arguments` / `bear_arguments` / `cost_usd` / `errors` 走 reducer 合并；其他 slot 由单一节点写入，避免合并冲突。
- 在系统边界处再用 Pydantic（`NewsItem` / `MarketSnapshot`）做严格校验。

### 2.4 模型路由

| 层级 | 模型 | 场景 |
|---|---|---|
| 高 | `claude-opus-4-7` | **Trader 决策**（高 stakes，仅在 conviction≥0.6 时调用） |
| 中 | `claude-sonnet-4-6` | 分析师（4 个）+ Bull/Bear + Judge + Macro + Reflection |
| 低 | `claude-haiku-4-5-20251001` | NewsCollector（高吞吐、低单价） |

每次 LLM 调用在 [llm/client.py](src/newsalpha/llm/client.py) 包装层里：

- 走 **prompt caching**（顶层 `cache_control` 断点，预期节省 40-60% input token）
- 按 model 单价分别计 cache hit / miss 成本，写入 `state.cost_usd`
- `tenacity` 指数退避重试 3 次
- JSON 解析容错（`_try_parse_json` 兜底返回 None，不抛异常）
- 日预算熔断：`LLM_DAILY_BUDGET_USD=20.0`，超额则后续调用直接拒绝

---

## 3. 12个智能体细节

### 3.1 总览

| # | Agent | 模型 | 输入要点 | 关键输出字段 | 引入周 |
|---|---|---|---|---|---|
| 1 | **NewsCollector** | Haiku 4.5 | 触发器 + 数据源 | `news_items[]`（含 event_id / summary / category） | W1 |
| 2 | **SentimentAnalyst** | Sonnet 4.6 | news + market_snapshot | `polarity ∈ [-1,1]`, `confidence`, `horizon` | W2 |
| 3 | **FundamentalAnalyst** | Sonnet 4.6 | news + 基本面字段 | `scores`（5 维）, `event_driven`, `citations` | W2 |
| 4 | **TechnicalAnalyst** | Sonnet 4.6 | 确定性 TA 面板 | `signals[]`, `overall_bias`, `panel`（透传） | W2 |
| 5 | **MacroAnalyst** | Sonnet 4.6 | FRED 面板（VIX/收益率/趋势） | `regime`, `regime_weight ∈ [0.3, 1.0]` | W5 |
| 6 | **BullResearcher** | Sonnet 4.6 (T=0.4) | 分析师 + 历史轮论点 | `claims[]`（每条必引证据 id）+ `conviction` | W3 |
| 7 | **BearResearcher** | Sonnet 4.6 (T=0.4) | 同上 + 区分 risk / thesis | `claims[]` + `rebuts_bull_id` | W3 |
| 8 | **DebateJudge** | Sonnet 4.6 (T=0.1) | 完整辩论记录 | `winner / directional_bias / conviction` + 5 维评分 | W3 |
| 9 | **Trader** | **Opus 4.7** | judge 裁决 + 分析师 + 持仓 | `action / size / stop / take_profit` | W3 |
| 10 | **RiskManager** | (纯 Python) | trade_signal | `RiskDecision`（accepted/reasons/adjustments） | W3 |
| 11 | **PortfolioManager** | (纯 Python) | RiskManager + macro_report | 改写 `final_orders[].size_pct` + audit | W5 |
| 12 | **ReflectionAgent** | Sonnet 4.6 | 平仓事件 + 决策快照 | `Episode`（what_worked/failed/lessons） | W4 |

### 3.2 分析师层：并行 fan-out

四个分析师同时执行，写入**不相交**的 state slot 避免合并冲突：

```python
g.add_edge("news_collector", "sentiment_analyst")
g.add_edge("news_collector", "fundamental_analyst")
g.add_edge("news_collector", "technical_analyst")
g.add_edge("news_collector", "macro_analyst")
g.add_edge("sentiment_analyst",   "analysts_ready")
g.add_edge("fundamental_analyst", "analysts_ready")
g.add_edge("technical_analyst",   "analysts_ready")
g.add_edge("macro_analyst",       "analysts_ready")
```

`analysts_ready` 是同步屏障节点（pure no-op），等待所有分析师完成才推进。

**TA 工具层（[tools/ta/indicators.py](src/newsalpha/tools/ta/indicators.py)）**：纯 Python，零原生依赖，提供 RSI / EMA / MACD / ATR / VWAP / 朴素 S-R / `summarize()` 一站式面板。TechnicalAnalyst **不计算**任何指标，只**解释**面板 —— 把数字算错的代价（高）与叙事写错的代价（低）正确分工。

**关键 bug 修复（W2 留下的痕迹）**：RSI 在纯单边行情下分母为 0 会级联 NaN。改用四个 `where` 条件：纯涨→100，纯跌→0，双 0→50，正常情况标准公式。

### 3.3 辩论层：A/B 可切换机制（差异化亮点 #1）

辩论是项目相较于 [TradingAgents](https://arxiv.org/abs/2412.20138) 的第一大差异化点。三种模式在 [configs/agents.yaml](configs/agents.yaml) 的 `debate.mode` 字段切换，**图结构完全不变**：

| 模式 | 流程 | 用途 |
|---|---|---|
| `adversarial` | Bull 立论 → Bear 必须按 id 引用 + 反驳 → Judge | 默认；强对抗，最大化暴露反方案视角 |
| `panel` | Bull 与 Bear 独立陈述 → Judge 综合 | 减少 Bear 的"反驳偏倚"，看双方独立强论点 |
| `socratic` | Judge 出引导问题 → 双方回答 → 展开 → Judge 终审 | 适合复杂事件，强迫双方先回答关键问题 |

切换零成本意味着可以做严肃的 A/B 实验：哪种机制在哪类事件（earnings / M&A / macro shock）上决策准确率更高。

**辩论编排细节**（[debate_orchestrator.py](src/newsalpha/agents/debate_orchestrator.py)）：

- `debate_orchestrator`：seed 首轮的 `debate_round=1` 与 `debate_mode`
- `debate_round_advancer`：每对 Bull+Bear 完成后 round++
- `should_continue_debate`：当 `next_round ≤ max_rounds` 返回 `continue` 回到 bull，否则 `judge`
- `should_trade`：Judge 后路由 — `bias != neutral AND conviction ≥ 0.6 → trade`，否则 `log_only → END`

**append-only 累积**：`bull_arguments` / `bear_arguments` 用 `Annotated[list, add]` 实现多轮自然累积，每条 claim 必须引用证据 id（Bull）或反驳目标 id（Bear），形成完整证据链。

### 3.4 Trader 短路：成本与风险姿态对齐

[trader.py](src/newsalpha/agents/trader.py:45) 的关键逻辑：

```python
if bias == "neutral" or conv < 0.6:
    return {"trade_signal": _hold_signal(ticker, f"hold: bias={bias} conviction={conv:.2f}")}
```

弱信号下**不发起 Opus 调用**，同时实现两个目标：

1. **省 token** — Opus 4.7 单次 ~$0.03，弱信号不该烧
2. **风控姿态** — 系统级偏好"少错过不如少错"，与 README 免责声明一致

### 3.5 信任边界 #1：RiskManager（[risk/rules.py](src/newsalpha/risk/rules.py)）

**永不调用 LLM**。按顺序应用 7 条规则，每条都可单测、可配置、可审计：

| # | 规则 | 行为 | 配置项 |
|---|---|---|---|
| 1 | `hold` 短路 | 拒绝 + reason `trader_recommended_hold` | — |
| 2 | 单票上限 5% NAV | **clamp 而非拒绝** + `size_capped` 告警 | `position.max_single_pct` |
| 3 | 持仓 headroom 检查 | clamp 到剩余空间 / 全部拒绝 | — |
| 4 | 强制止损 | 缺失时按 2×ATR(14) 回填 | `stops.atr_multiplier` |
| 5 | Long stop ≥ entry | 拒绝 | — |
| 6 | Short stop ≤ entry | 拒绝 | — |
| 7 | 流动性 < $10M/日 | 拒绝 | `universe_filter.min_avg_dollar_volume_usd` |

返回 `RiskDecision`，含 `accepted / reasons[] / adjustments[] / rule_versions{}` —— **rule_versions 字段把当时生效的阈值快照下来**，这样回放/审计才能精确还原"当时按什么规则做的决定"。

### 3.6 信任边界 #2：PortfolioManager（[agents/portfolio_manager.py](src/newsalpha/agents/portfolio_manager.py)）

**同样纯 Python，永不调用 LLM**。在 RiskManager 之后做最终仓位整形，sizing pipeline：

```
base_size (Trader 给)
    │
    ├── × regime_weight   ← MacroAnalyst 给：crisis 0.3 / bear 0.5-0.6 / chop 0.7-0.75 / bull 1.0
    ├── × conviction_factor   ← Judge conviction，<0.6 直接零
    ├── × kelly_factor     ← fractional Kelly @ 0.25
    ├── × vol_factor       ← target vol 0.15，clip [0.25, 1.5]×
    │
    ▼
final_size = min(..., max_single_pct=0.05)   ← 全程审计落 audit[]
```

实现见 [execution/sizing.py](src/newsalpha/execution/sizing.py)。每笔订单的 `sizing_breakdown` 都写进 `portfolio_decision.audit[]`，回放时可以精确看到每个因子如何把原始尺寸缩到最终值。

**为什么 PortfolioManager 也不能调 LLM？**

- 仓位计算是金融工程问题，不是叙事问题，LLM 没有比 Kelly 公式更好的答案
- 调 LLM 引入非确定性，回放就失去意义
- 信任边界要"可解释 + 可审计"，LLM 的概率性输出违背这两条

---

## 4. 三大差异化亮点完整体

### 4.1 亮点 #1：A/B 可切换辩论机制（W3 完成）

如 §3.3 所述，三种模式 `adversarial / panel / socratic` 仅改 YAML 即可切换，复用同一 LangGraph 拓扑。这给项目带来一个可写论文的方向：**辩论机制对不同事件类型的决策质量影响**。

### 4.2 亮点 #2：决策快照回放（W3 写入 → W4 完整体 → W5 Dashboard 可视化）

#### 设计目标

每次完整图运行的全量 state 落盘 → 任意时刻可"无成本"重跑下游：

- **风控参数 A/B**：改 `risk.yaml` 后 replay 历史决策，看哪些会被新规则拒绝
- **回测信号源**：扫所有 accepted 快照 → backtrader 信号流 → PnL
- **审计回放**：监管/复盘时还原任意历史决策的完整证据链

#### 关键 API

```python
from newsalpha.backtest.replay import replay_decision, extract_signals_for_backtest

# 单点风控 override
replayed = replay_decision(
    "data/snapshots/abc123_AAPL.json",
    override_risk_config={"position": {"max_single_pct": 0.001}},
)

# 扫全目录提信号
signals = extract_signals_for_backtest("data/snapshots/")
```

#### 三条原则

1. **Replay 不重新调 LLM** —— 信号、辩论、verdict 全部从快照取；只重跑 `risk.rules.evaluate_signal` 与 `portfolio_manager`（纯 Python，确定性）。这是"快照即真相"的具体兑现。
2. **JSON-on-disk 优先 vs Postgres** —— W4 优先打通回路；持久化层升级延后到接 Alpaca 时统一做。
3. **损坏快照不阻断** —— `extract_signals_for_backtest` 遇到坏 JSON 只 warn 不抛，一笔坏数据不能让整个回测炸。

#### Dashboard 可视化

Streamlit 的 "Replay (A/B)" 页：选快照 → 改风控参数 → 对比原始 vs 重放结果，差异点红色标记。

### 4.3 亮点 #3：Reflection 经验记忆（W4 写入 → W5 Dashboard 可视化）

#### 设计

```
平仓事件（backtest 或实盘）
    │
    ▼
ReflectionAgent.reflect_on_trade()
    │ ├ 输入：trade_log + decision_state（分析师报告 / 辩论记录）
    │ ▼
    │ LLM (Sonnet 4.6) → {what_worked[], what_failed[], lessons[], key_signals[]}
    │
    ▼
Episode → text_summary → embed_text() → 256-dim vector
    │
    ▼
write_episode() → Qdrant (or InMemoryEpisodeStore fallback)
    │
    ▼
[未来辩论]
retrieve_similar(query="AAPL bull earnings", ticker="AAPL", limit=3)
   → top-K 相似历史经验注入 Bull/Bear 上下文（v1.1 接入）
```

#### Episode schema（[memory/episodes.py](src/newsalpha/memory/episodes.py)）

```python
@dataclass
class Episode:
    ticker: str
    side: str
    entry_date: str
    exit_date: str
    pnl_pct: float
    conviction: float          # 入场时 judge 给的 conviction
    regime: str                # bull|bear|chop|crisis（由 MacroAnalyst 标注）
    what_worked: list[str]     # 哪些信号正确
    what_failed: list[str]     # 哪些信号失败
    lessons: list[str]         # 可复用教训
    key_signals: list[str]     # 决定性信号清单
    trace_id: str              # 链回原始决策快照
```

#### 关键工程选择

| 选择 | 理由 |
|---|---|
| **Hash-based 占位 embedding** | W4 不引入 embedding API，避免 Voyage/OpenAI/Anthropic 不一致；切真 embedding 只改 `embed_text()` 一个函数 |
| **InMemoryEpisodeStore fallback** | Qdrant 服务挂了不阻断工作流；`NEWSALPHA_MEMORY_BACKEND=memory` 强制内存模式 |
| **`reflect_batch()` 不调 LLM** | 回测时百笔 trade 走 LLM 太贵；规则化生成 lessons 模板，"真实的" reflection 留给实盘事件 |
| **episode_id = md5(ticker\|entry\|exit\|trace_id\|created_at)** | 同一笔交易反思可重复写（覆盖最新版）；不同笔通过 trace_id 区分 |

**当前限制**：`embed_text()` 是 SHA-256 哈希，**不是真正的语义检索**，仅用于把存储/检索管道跑通。v1.1 切 `voyage-3` 或 `text-embedding-3-large` 后才能产生真正有意义的相似历史召回。

---

## 5. 回测体系

### 5.1 短回测管道（W4 交付）

```
Snapshots (或 synth signals)
    │
    ▼ extract_signals_for_backtest()
    │
    ▼ run_multi_ticker_backtest()  [backtrader]
        │
        ├─ NewsAlphaStrategy（持有 pending_signals 队列）
        │   ├─ 每日 next() 检查止损/止盈
        │   └─ 弹出 as_of ≤ today 的信号 → buy/sell
        │
        ▼ trade_log + portfolio_values + returns
    │
    ▼ compute_all_metrics()
    │
    ▼ write_markdown_report() / generate_html_report()
```

### 5.2 关键设计选择

| 选择 | 替代方案 | 理由 |
|---|---|---|
| **Pre-computed signals 输入策略** | 策略内反向调 LangGraph 实时生成 | 保持回测**确定性**；LLM 调用昂贵且非确定 |
| **`params.signals` 注入而非全局** | 全局变量 | 多 ticker × 多 cerebro 并行时不会串信号 |
| **`commission=0.001`** | 0 / 真实 fee schedule | 10bps 是 Alpaca/IBKR 平均费率合理近似 |
| **Mock-or-yfinance 走 connector 抽象** | 硬绑 yfinance | CI 与离线开发友好 |
| **`stop()` 钩子强平所有仓位** | 让仓位悬空 | 避免 PnL 漏统计 |

### 5.3 性能指标库（[backtest/metrics.py](src/newsalpha/backtest/metrics.py)）

纯 numpy/pandas，95% 覆盖：

| 函数 | 边界处理 |
|---|---|
| `sharpe_ratio(returns)` | `std<1e-12 → 0`；空 series → 0 |
| `sortino_ratio(returns)` | 无下行波动 → ∞ 或 0 |
| `max_drawdown(returns)` | 空 → 0，否则 ≤ 0 |
| `cagr(returns)` | 总收益 ≤ 0 → 0 |
| `win_rate(trades)` / `profit_factor(trades)` | 全胜 → ∞；空 → 0 |
| `compute_all_metrics(...)` | 一次性算完整套；含基准 → 加 alpha_vs_benchmark |

**坑点**：`pd.Series([0.001]*100).std()` 返回 ~1e-19（浮点精度伪 0），不是真 0 —— Sharpe 飙到 7e16。改用 `std < 1e-12` 容差判断后修复。

### 5.4 长回测 2020-2025（W6 交付）

#### 4 个 Regime 段设计

| 段 | 时间 | Regime | long_bias | conviction | size | 信号/票 |
|---|---|---|---|---|---|---|
| `covid_crisis` | 2020-02 → 2020-06 | crisis | 0.30 | 0.55-0.75 | 0.01-0.03 | 8 |
| `bull_2021` | 2021-01 → 2021-12 | bull | 0.80 | 0.70-0.95 | 0.03-0.05 | 12 |
| `bear_2022` | 2022-01 → 2022-12 | bear | 0.35 | 0.60-0.80 | 0.02-0.04 | 10 |
| `recovery_2023_24` | 2023-01 → 2024-12 | bull | 0.70 | 0.65-0.90 | 0.03-0.05 | 15 |

#### 设计意图

直接调 LLM 跑 5 年成本不切实际（粗算需要数千美元）。换思路：用 **regime 校准的合成信号**，模拟"如果系统真在那段历史中运行，理论行为会怎样"：

- 危机期：长偏 30%，小尺寸，低 conviction → 防御姿态
- 牛市期：长偏 80%，大尺寸，高 conviction → 进攻姿态
- 熊市期：长偏 35%，平衡多空 → 中性姿态
- 恢复期：长偏 70%，逐步加大 → 渐进进攻

这样长回测验证的不是 LLM 决策的 alpha，而是 **MacroAnalyst → PortfolioManager 的 regime-aware sizing 在各 regime 下的姿态对齐能力**。

#### 端到端验证

Mock 数据下跑通：

- 8 ticker × 4 segments × 平均 11 信号/票 = **360 信号**
- 实际成交 **305 trades**（其余因 stop/tp 价位与合成价格不匹配未触发）
- 4 段 + 全期 metrics 全部输出
- 自动产出：`long_backtest_<ts>.md` + `metrics_long_<ts>.json` + 标准 `backtest_long_<ts>.md`

> **重要免责**：mock 数据下指标接近零属预期（合成价格 = 随机游走 + 合成信号无真 alpha）；切真 yfinance 数据后才有意义对比。这是 v1.1 路线项。

---

## 6. 执行层

### 6.1 Broker 抽象（[execution/broker.py](src/newsalpha/execution/broker.py)）

```
BaseBroker (ABC)
├── MockBroker          ← 内存确定性，测试 + 回测；模拟完整持仓 + 现金扣减 + order log
└── AlpacaBroker        ← alpaca-py SDK，paper / live
    └── confirm_live=True 才允许 BROKER_MODE=live
```

### 6.2 双重安全开关

实盘下单需要**同时满足**两个条件，缺一不可：

```python
# 1. 环境变量
BROKER_MODE=live

# 2. 构造时显式确认
AlpacaBroker(confirm_live=True)
```

否则在 `__init__` 阶段就 `RuntimeError`。这是工程层面把"误触发实盘"的概率降到接近零的设计 —— 单一开关在重构/合并时容易被错改，两个独立位置的开关需要两步独立确认。

工厂方法 `get_default_broker()` 的优先级：

```
NEWSALPHA_BROKER=mock → MockBroker
缺 Alpaca 凭证        → MockBroker（warn）
有凭证 + BROKER_MODE=paper → AlpacaBroker(paper)
有凭证 + BROKER_MODE=live + confirm_live=True → AlpacaBroker(live)
```

### 6.3 Sizing Pipeline 完整公式

见 §3.6。每笔订单的最终尺寸都通过 5 个独立因子（base × regime × conviction × kelly × vol）相乘并 clip 到单票上限，全程在 `portfolio_decision.audit[]` 留痕。

---

## 7. 对外接口

### 7.1 FastAPI（[api/app.py](src/newsalpha/api/app.py)）

| Method | Path | 功能 |
|---|---|---|
| GET | `/health` | 健康检查 |
| GET | `/snapshots` | 列出所有决策快照 |
| GET | `/snapshots/{id}` | 获取单个快照 |
| POST | `/decisions/replay` | 风控参数 override 重放 |
| GET | `/memory/episodes` | 列出最近 reflection 记忆 |
| POST | `/run` | 触发一次完整图运行 |
| WS | `/ws/events` | 实时事件流（pub/sub） |

启动：`uv run uvicorn newsalpha.api.app:app --reload` 或 `make api`

### 7.2 Streamlit Dashboard（6 页）

| 页面 | 功能 |
|---|---|
| **Decisions** | 所有快照列表 + conviction/bias/accept 指标 + JSON 展开 |
| **Decision Graph** | 5 种 Plotly 图（Sankey 信号流 + Bar 节点吞吐 + Pie regime 分布 + Histogram conviction 分布 + Box 延迟） |
| **Debate Viewer** | Bull vs Bear arguments 对照 + Judge verdict |
| **Backtest** | 从 `data/reports/` 加载指标 + Markdown 报告 |
| **Memory** | 最近 30 条 reflection episodes |
| **Replay (A/B)** | 选快照 → 改风控参数 → 对比原始 vs 重放 |

启动：`uv run streamlit run src/newsalpha/dashboard/app.py` 或 `make dashboard`

### 7.3 命令行入口

```
make demo          # python -m newsalpha.demo           — hello-world 验证
make backtest      # python -m newsalpha.backtest.cli   — 合成信号一年回测
make long-backtest # python -m newsalpha.backtest.long_backtest — 2020-2025 4 段
make api           # uvicorn 启 FastAPI
make dashboard     # streamlit 启 UI
make test          # pytest 全套 123 测试
```

---

## 8. 测试体系

### 8.1 测试矩阵（19 个文件 / 123 个测试）

| 文件 | 测试数 | 覆盖范围 |
|---|---|---|
| `test_graph_w1.py` | 2 | W1 端到端 demo 图 |
| `test_llm_routing.py` | 4 | per-agent 模型/参数加载 |
| `test_llm_client_json.py` | 3 | JSON 解析容错 |
| `test_connectors.py` | 5 | 新闻 + 行情连接器（mock + yfinance） |
| `test_ta_indicators.py` | 9 | RSI / EMA / MACD / ATR / VWAP / 边界情况 |
| `test_agents.py` | 8 | 4 个分析师独立单测 |
| `test_graph_w2.py` | 3 | 分析师并行 fan-out 集成 |
| `test_debate_and_decision.py` | 17 | Bull/Bear/Judge/Trader 全链路 + 短路 |
| `test_graph_w3.py` | 2 | W3 端到端（含 conviction 路由） |
| `test_snapshots.py` | 4 | 快照写入/读取/编码容错 |
| `test_replay.py` | 5 | Replay + 风控 override + 损坏容错 |
| `test_backtest_engine.py` | 5 | backtrader 集成 + 多 ticker 聚合 |
| `test_metrics_and_reports.py` | 14 | 6 个指标函数 + HTML/MD 报告 |
| `test_memory.py` | 8 | Episode schema + Qdrant + InMemory + 检索 |
| `test_execution.py` | 16 | Broker (Mock + Alpaca 安全开关) + Sizing pipeline |
| `test_macro_and_portfolio.py` | 9 | MacroAnalyst 4 regime + PortfolioManager 调仓 |
| `test_graph_w5.py` | 2 | W5 端到端（12 agent 闭合） |
| `test_long_backtest.py` | 6 | 4 regime 覆盖 + long_bias 校准 + 确定性 |
| `test_decision_graph.py` | 9 | 5 个 Plotly figure builder + 空数据兜底 |
| **合计** | **123** | — |

### 8.2 覆盖率

| 模块 | 覆盖率 | 备注 |
|---|---|---|
| `core/state.py` | 100% | TypedDict 简单 |
| `core/graph.py` | 100% | 端到端测试覆盖 |
| `risk/rules.py` | ~95% | 全部 7 条规则路径有测试 |
| `backtest/replay.py` | 100% | — |
| `backtest/metrics.py` | 95% | — |
| `backtest/engine.py` | 84% | — |
| `execution/sizing.py` | 100% | — |
| `agents/macro_analyst.py` | 98% | — |
| `agents/portfolio_manager.py` | 100% | — |
| `execution/broker.py` | 63% | AlpacaBroker 实际 API 调用未在 CI 跑 |
| `data/connectors/news.py` | 44% | Finnhub 路径未补集成测试 |

**核心模块（state/graph/risk/replay/metrics/sizing/portfolio_manager）全在 95%+**，是项目"能审"的硬支撑。

### 8.3 测试策略关键决策

| 决策 | 理由 |
|---|---|
| **monkeypatch 必须覆盖所有 agent 模块的 namespace** | 每个 agent 用 `from .base import call_agent`，patch base 模块不够；必须遍历每个 agent 模块逐个 patch（W5 期间踩过坑） |
| **Mock 三件套**：`NEWSALPHA_MOCK_DATA=1 + NEWSALPHA_MEMORY_BACKEND=memory + NEWSALPHA_BROKER=mock` | 完整离线 CI；任一 connector / 存储 / broker 都有 mock fallback |
| **集成测试断言 cost_usd ≥ 0** | 即使 mock，cost reducer 应正确累加；这是 reducer 正确性的最便宜断言 |
| **回测断言 trades 数 > 0** | 端到端 smoke 而非精确 PnL（mock 数据下 PnL 不可信） |

---

## 9. 配置与目录结构

### 9.1 目录布局

```
newsalpha/
├── configs/
│   ├── agents.yaml              # per-agent 模型路由 + 辩论模式 + 阈值
│   ├── risk.yaml                # 风控阈值
│   ├── universe.yaml            # 股票池
│   └── prompts/system/          # 9 个 agent 的 markdown 提示词
│       ├── sentiment_analyst.md
│       ├── fundamental_analyst.md
│       ├── technical_analyst.md
│       ├── macro_analyst.md
│       ├── bull_researcher.md
│       ├── bear_researcher.md
│       ├── debate_judge.md
│       ├── trader.md
│       └── reflection.md
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
│   ├── dashboard/               # Streamlit + Plotly 决策图谱
│   └── utils/                   # logging
├── tests/unit/                  # 19 个测试文件，123 tests
└── docs/                        # W1-W6 阶段报告 + architecture
```

### 9.2 关键配置文件示例

`configs/agents.yaml`（节选）：

```yaml
debate:
  mode: adversarial               # adversarial | panel | socratic
  rounds: 2
  min_conviction_to_trade: 0.6

llm:
  daily_budget_usd: 20.0

agents:
  trader:
    model: claude-opus-4-7
    # 不设 temperature（Opus 不支持采样参数）
  bull_researcher:
    model: claude-sonnet-4-6
    temperature: 0.4
```

`configs/risk.yaml`（节选）：

```yaml
position:
  max_single_pct: 0.05            # 单票 5% NAV
  max_sector_pct: 0.25

stops:
  atr_multiplier: 2.0

universe_filter:
  min_avg_dollar_volume_usd: 10_000_000

leverage:
  max: 1.0                        # MVP 不加杠杆

earnings_blackout_hours: 24       # 财报前 24h 不开仓
drawdown_circuit_breaker_pct: 0.10
```

---

## 10. 技术栈

| 层 | 技术 |
|---|---|
| **LLM** | Anthropic Claude (Opus 4.7 / Sonnet 4.6 / Haiku 4.5) + prompt caching |
| **编排** | LangGraph (StateGraph + parallel fan-out + Annotated reducer) |
| **数据** | yfinance · Finnhub · NewsAPI · FRED · Mock connectors |
| **回测** | backtrader · quantstats（HTML tear sheet） |
| **向量存储** | Qdrant (prod) · InMemoryEpisodeStore (dev/test) |
| **执行** | Alpaca paper/live · MockBroker |
| **API** | FastAPI · WebSocket（pub/sub EventBus） |
| **可视化** | Streamlit · Plotly（Sankey + Bar + Pie + Histogram + Box） |
| **配置** | pydantic-settings · YAML |
| **测试** | pytest + monkeypatch（123 tests / 19 files） |
| **质量** | ruff · mypy · pre-commit |
| **运行时** | uv + Python 3.11+ |
| **基础设施** | docker-compose（Postgres + Qdrant + Redis） |

---

## 11. 关键设计决策汇总

8 条最值得讲的设计决策（按"问什么答什么"的密度排序）：

| # | 决策 | 理由 |
|---|---|---|
| 1 | **TypedDict + `Annotated[..., add]`** | LangGraph 原生 reducer 支持，并行 fan-out 合并多 agent 写入 |
| 2 | **数字算 Python，叙事算 LLM** | TA 指标 / 风控规则 / 仓位计算全确定性；LLM 只解释，不计算 |
| 3 | **辩论模式 A/B 通过 prompt + config 切换** | 复用同一 LangGraph 拓扑，研究不同辩论机制对决策质量的影响 |
| 4 | **Trader 在低 conviction 时短路 hold** | 弱信号下不发 Opus 调用 — 省 token + 对齐"宁错过不错杀" |
| 5 | **RiskManager / PortfolioManager 永不调用 LLM** | LLM 判断与真金白银的信任边界；硬规则可审计可回放可单测 |
| 6 | **每次决策落盘全量 state** | 快照即真相，是回放 / 复盘 / Reflection 的唯一数据源 |
| 7 | **Replay 不重新调 LLM** | 只重跑 `risk.rules.evaluate_signal` 与 `portfolio_manager` |
| 8 | **Live mode 需 `confirm_live=True` + `BROKER_MODE=live`** | 默认 paper；实盘双重确认，构造时即失败 |

---

## 12. 已知限制

按"严重程度 × 影响范围"排序：

### 12.1 数据真实性

- **长回测在 mock 模式验证管道** — 真实 yfinance 数据下需重跑才能获得有意义指标
- **`embed_text()` 是 SHA-256 哈希占位**，不是真 embedding —— Reflection 检索目前没有真正的语义相似度，只能 by-ticker 过滤
- **长回测合成信号不依赖真新闻** — 真闭环需要历史新闻流（订阅 Finnhub 历史 API）

### 12.2 覆盖与测试

- **AlpacaBroker live mode 未在 CI 测试**（需 paper 账号凭证）— broker.py 63% 覆盖
- **News connector Finnhub 路径 44% 覆盖**（W2 留下，W4-W6 未碰）
- **demo.py 0% 覆盖**（CLI 入口，靠手动验证）

### 12.3 工程债

- **FastAPI 无鉴权** — 本地/研究无碍，部署前需补 JWT/API-key
- **Dashboard 未直接订阅 WebSocket** — 当前为页面刷新模式
- **Reflection 检索未注入 Bull/Bear 上下文** — 写入侧 OK，读取侧待 v1.1
- **Backtest slippage 模型未建** — 仅 commission 1bps（10bps 双边可接受）
- **TA 指标默认参数** — 没做参数优化（避免过拟合，但实盘前需 walk-forward）

### 12.4 可观测性

- **LangSmith trace 推迟到生产部署** — 当前依赖 structlog 文本日志
- **无 Prometheus metrics** — Sharpe / win-rate / cost-per-decision 等需要看 dashboard 或 JSON
- **无告警** — 日预算熔断只是拒绝调用，没有飞书/Slack 通知

---

## 13. v1.x 路线（可选）

| 版本 | 主题 | 预计工时 |
|---|---|---|
| **v1.1** | 真 yfinance 长回测 + Voyage-2 embedding + Reflection 注入辩论上下文 | 1 周 |
| **v1.2** | LangSmith trace + Prometheus metrics + 飞书告警 | 1 周 |
| **v1.3** | Walk-forward TA 参数优化 + slippage model + commission schedule | 1 周 |
| **v1.4** | Next.js 决策图谱（替代 Streamlit）+ Vercel 部署 + 公开 demo URL | 2 周 |

按优先级：**v1.1 > v1.3 > v1.2 > v1.4**。v1.1 解决"真数据下系统跑得怎么样"这个面试官最关心的问题；v1.3 让回测更接近真实交易成本；v1.2 是生产工程素养；v1.4 是公开 demo。

---

## 14. 合规与安全

### 14.1 已落地

| 措施 | 实现 |
|---|---|
| 默认 paper mode | `BROKER_MODE=paper` 在 [config.py](src/newsalpha/core/config.py) 强制 |
| 实盘双重确认 | `BROKER_MODE=live` + `AlpacaBroker(confirm_live=True)` 缺一不可 |
| LLM 日预算熔断 | `LLM_DAILY_BUDGET_USD=20.0`；超限 raise → 节点静默跳过 |
| 不分发原始新闻文本 | 只保留 `summary` + `event_id`（合规于 Benzinga / Finnhub TOS） |
| 免责声明 | README 显著标注："研究 / 演示用途，不构成投资建议" |
| RiskManager 永不调 LLM | 信任边界硬约束 |
| PortfolioManager 永不调 LLM | 信任边界硬约束 |

### 14.2 实盘前待补（即使是 paper 账号也建议先做）

- JWT/API-key 保护 FastAPI 端点
- 操作审计日志（who / when / what config change）
- Drawdown circuit breaker 真实接 Alpaca cancel_all + 暂停 24h
- LangSmith trace + 异常告警

---

## 15. 项目自评

### 15.1 招聘场景的差异化讲法

| 维度 | 我们的做法 | 区别于市面常见项目 |
|---|---|---|
| **Agent 架构** | 12 个 LangGraph 节点，并行 fan-out + 迭代辩论 + 双信任边界 | ≠ 单 prompt + 工具调用循环 |
| **回测** | 决策快照 → 信号 → backtrader → quantstats；Replay 不重调 LLM | ≠ 直接喂历史价格让 LLM "假装" 决策 |
| **风控** | 100% 纯 Python 规则，可单测、可回放、可审计 | ≠ "让 LLM 评估风险"或纯 vibe-check |
| **存储** | TypedDict 全量快照 + Qdrant episode 记忆 + 决策日志 | ≠ 只存 final order |
| **可视化** | 5 种 Plotly 图 + Sankey 信号流 + A/B Replay UI | ≠ 仅打印日志 |
| **安全** | paper 默认 + live 双重确认 + LLM 日预算熔断 + 信任边界 | ≠ "demo 跑通就好" |

### 15.2 完成度判断

按 6 周原计划：

- ✅ 12 智能体闭合
- ✅ A/B 辩论机制（差异化 #1）
- ✅ 决策快照 Replay 完整体（差异化 #2）
- ✅ Reflection 记忆写入侧（差异化 #3）
- ✅ Backtest 引擎 + quantstats
- ✅ AlpacaBroker + 安全开关
- ✅ FastAPI + Streamlit 6 页 dashboard
- ✅ 长回测 4 regime 段
- ✅ 决策图谱 5 种 Plotly 可视化
- ✅ README + architecture.md + Makefile v1.0
- 🟡 Reflection 检索注入辩论上下文 → v1.1
- 🟡 真 yfinance 数据下的长回测 → v1.1
- 🟡 LangSmith trace + 生产监控 → v1.2

**结论：v1.0 完整收官。123 个测试全绿，文档与可演示性达到招聘投递标准。**

### 15.3 适合做的延伸演示

面试现场可以演示的 3 个 5 分钟 demo：

1. **"决策可回放"演示** — 跑 `make demo` 落一个快照 → 改 `risk.yaml` 单票 5% → 1% → `make api` 后 POST `/decisions/replay` → 看同一笔信号在新规则下被拒绝
2. **"辩论 A/B"演示** — 改 `configs/agents.yaml` 的 `debate.mode` 从 `adversarial` 到 `socratic` → 重跑 demo → 在 Dashboard 看两次的 Bull/Bear 论点结构差异
3. **"长回测 regime 对比"演示** — `make long-backtest` → 在 Dashboard "Decision Graph" 页面看 Sankey 信号流 + regime pie 在 4 段中的差异

---

## 16. 项目回顾

6 周内交付：

- **54 个 Python 模块**（4,946 行源码）
- **123 个单元测试**（19 个文件，2,008 行；全绿）
- **5 篇阶段报告 + 1 篇架构文档 + 本总报告**
- **12 个 Claude 智能体**（Opus + Sonnet + Haiku 三层路由）
- **5 个对外接口**（CLI / FastAPI / WebSocket / Streamlit / 直接 Python API）

这是一个**面向招聘场景的"能跑、能讲、能审"的多智能体量化交易系统 demo**。所有代码可在 mock 模式离线运行，零 API 成本即可演示完整闭环。

---

## 附录 A：完整文件清单

### A.1 阶段报告

- [W1-W3_REPORT.md](W1-W3_REPORT.md) — 基础设施 + 分析师层 + 辩论决策核心
- [W4_REPORT.md](W4_REPORT.md) — 回测引擎 + Replay + Reflection 写入
- [W5_REPORT.md](W5_REPORT.md) — 执行层 + Macro + Portfolio + API + Dashboard
- [W6_REPORT.md](W6_REPORT.md) — 长回测 + 决策图谱 + v1.0 收官
- [architecture.md](architecture.md) — 5 层架构索引

### A.2 关键源码入口

- 状态契约：[src/newsalpha/core/state.py](src/newsalpha/core/state.py)
- LangGraph 拓扑：[src/newsalpha/core/graph.py](src/newsalpha/core/graph.py)
- 信任边界 #1：[src/newsalpha/risk/rules.py](src/newsalpha/risk/rules.py)
- 信任边界 #2：[src/newsalpha/agents/portfolio_manager.py](src/newsalpha/agents/portfolio_manager.py)
- 决策快照与回放：[src/newsalpha/backtest/replay.py](src/newsalpha/backtest/replay.py)
- 长回测：[src/newsalpha/backtest/long_backtest.py](src/newsalpha/backtest/long_backtest.py)
- 决策图谱可视化：[src/newsalpha/dashboard/decision_graph.py](src/newsalpha/dashboard/decision_graph.py)
- Reflection 记忆：[src/newsalpha/memory/episodes.py](src/newsalpha/memory/episodes.py)
- Broker 抽象：[src/newsalpha/execution/broker.py](src/newsalpha/execution/broker.py)

### A.3 关键配置入口

- Agent 路由 + 辩论模式：[configs/agents.yaml](../configs/agents.yaml)
- 风控阈值：[configs/risk.yaml](../configs/risk.yaml)
- 股票池：[configs/universe.yaml](../configs/universe.yaml)
- Agent prompts：[configs/prompts/system/](../configs/prompts/system/)

---

> 本报告由项目主理人编制，记录 NewsAlpha 自 2026-04 至 2026-05-28 共 6 周的设计、实现、取舍与限制。
> 系统为研究 / 演示用途，所有信号与回测结果**不构成投资建议**。
