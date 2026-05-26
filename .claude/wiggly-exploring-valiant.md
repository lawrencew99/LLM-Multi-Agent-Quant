# NewsAlpha — 新闻舆情驱动的多智能体美股交易系统

## Context

用户希望从零构建一个**生产原型级量化项目**，用于作品集/求职展示。场景锁定在**事件驱动 + LLM 多智能体辩论**，目标是比同类开源项目（TradingAgents, arxiv 2412.20138）有明确差异化。

核心约束：
- 框架：LangGraph（Python）
- 市场：美股，默认 Alpaca paper trading
- LLM：Anthropic Claude（Opus 4.7 决策，Sonnet 4.6 分析，Haiku 4.5 采集）
- 工期：6 周，渐进式智能体扩展（W1-4 精简 8 个，W5-6 补全 12 个）
- 前端：Streamlit（W5）→ Next.js（W6+）
- 差异化三大亮点：**A/B 辩论机制 + 决策快照回放 + Reflection 记忆**

---

## 系统架构

### 整体数据流

```
新闻 WebHook / 定时轮询
  (Finnhub + Alpaca Benzinga + SEC EDGAR)
          │
    Redis Streams ← 事件总线
          │
   NewsCollector (Haiku 4.5) → 标准化新闻对象
          │
    ┌─────┴──────┬──────────┬──────────┐
    ▼            ▼          ▼          ▼
 Sentiment   Fundamental Technical  Macro*
 Analyst     Analyst     Analyst    Analyst*
 (Sonnet)    (Sonnet)    (Sonnet)   (Sonnet)
    └─────┬──────┴──────────┘
          ▼
  BullResearcher ⇄ BearResearcher   ← 多轮辩论 (A/B 可配置机制)
          │
     DebateJudge (Sonnet)
          │
       Trader (Opus 4.7)
          │
     RiskManager (Opus 4.7) ← 硬规则，确定性 Python
          │
  PortfolioManager* (Opus 4.7)
          │
   AlpacaBroker (paper/live)
          │
  [平仓后异步] ReflectionAgent* → Qdrant 向量记忆
```

> `*` 标注的为 W5-6 渐进加入

### LangGraph StateGraph 关键设计

**State Schema**（`src/newsalpha/core/state.py`）：
```python
class TradingState(TypedDict):
    trigger: dict           # {event_id, ticker, ts}
    ticker: str
    as_of: str              # ISO，严格防 lookahead

    news_items: list[dict]
    market_snapshot: dict
    macro_context: dict

    sentiment_report: dict | None
    fundamental_report: dict | None
    technical_report: dict | None
    macro_report: dict | None

    bull_arguments: Annotated[list[dict], add]
    bear_arguments: Annotated[list[dict], add]
    debate_round: int
    debate_mode: str        # "adversarial" | "panel" | "socratic"
    judge_verdict: dict | None

    trade_signal: dict | None
    risk_decision: dict | None
    final_orders: list[dict]

    cost_usd: float
    latency_ms: int
    trace_id: str
    errors: list[str]
```

**执行路径**：
```
START → news_collector
  → [并行 fan-out] sentiment / fundamental / technical / macro
  → [join] debate_orchestrator
      → bull_researcher → bear_researcher
         ↑ if round < N (默认 2)  ↓ if round == N
                            debate_judge
                               ↓
              conviction < 0.6 → log_only → END
              conviction ≥ 0.6 → trader → risk_manager
                                   rejected → log_only → END
                                   accepted → portfolio_manager → order_executor → END
[异步] reflection_agent（平仓事件触发）
```

---

## 智能体角色卡（精简→完整渐进）

| # | 角色 | 模型 | W1-4 | W5-6 |
|---|------|------|------|------|
| 1 | NewsCollector | Haiku 4.5 | ✅ | ✅ |
| 2 | SentimentAnalyst | Sonnet 4.6 | ✅ | ✅ |
| 3 | FundamentalAnalyst | Sonnet 4.6 | ✅ | ✅ |
| 4 | TechnicalAnalyst | Sonnet 4.6 | ✅ | ✅ |
| 5 | BullResearcher | Sonnet 4.6 | ✅ | ✅ |
| 6 | BearResearcher | Sonnet 4.6 | ✅ | ✅ |
| 7 | DebateJudge | Sonnet 4.6 | ✅ | ✅ |
| 8 | Trader + RiskManager | Opus 4.7 | ✅(合并) | 拆分 |
| 9 | MacroAnalyst | Sonnet 4.6 | — | ✅ W5 |
| 10 | PortfolioManager | Opus 4.7 | — | ✅ W5 |
| 11 | ReflectionAgent | Sonnet 4.6 | — | ✅ W5 |

---

## 数据层

| 类型 | 选型 | 理由 |
|------|------|------|
| 实时新闻 | Finnhub + Alpaca Benzinga | Finnhub 免费层慷慨(60/min)；Alpaca WebSocket 实时流 |
| 重大事件 | SEC EDGAR 8-K | 权威，免费，必选 |
| 行情(实时) | Alpaca IEX 免费档 | 与交易账户同平台 |
| 行情(历史) | yfinance 日线 + Polygon flat files | 日线免费够 MVP，分钟线按需付费 |
| 宏观 | FRED API | 免费，Fed/CPI/利率 |
| 向量库 | Qdrant (Docker) | 生产级，支持 payload 过滤 |
| 时序 | Parquet + DuckDB | 零运维，SQL 直查 |
| 关系 | Postgres 15 | 决策日志/订单记录 |
| 事件总线 | Redis Streams | 单机够用，消费组天然支持 |

---

## 三大差异化亮点实现

### 1. A/B 辩论机制（`configs/agents.yaml`）

```yaml
debate:
  mode: adversarial   # adversarial | panel | socratic
  rounds: 2
```

- `adversarial`：Bull 先立论，Bear 主动攻击每一条
- `panel`：两者独立输出，Judge 综合
- `socratic`：Judge 反问驱动，Bull/Bear 逐步深化

切换时只修改 config，图结构不变。通过 A/B 对比不同机制的决策准确率。

### 2. 决策快照回放（`src/newsalpha/backtest/replay.py`）

- 每次图运行时，把所有 agent 的 `input + output + raw_llm_response` 写入 Postgres
- 回放时从 DB 读取快照，跳过 LLM 调用（确定性）
- 支持"只替换某节点 prompt"后重跑下游 → 消融实验/提示词 A/B
- 接口：`replay_decision(trace_id, override_agents=["bull_researcher"])`

### 3. Reflection 记忆（`src/newsalpha/memory/`）

平仓后异步触发：
1. 计算该笔交易 PnL、attribution（新闻贡献 vs 市场贡献）
2. ReflectionAgent 生成 `{what_worked, what_failed, lessons, key_signals}`
3. 写入 Qdrant `episodes` collection，embedding = ticker + 事件类型 + 宏观 regime
4. 辩论时检索 top-3 相似历史案例注入 Bull/Bear 上下文

---

## 提示缓存策略

四层断点（稳定 → 易变）：
1. System prompt / 角色定义（5-10k tokens，几乎不变）→ cache hit ~95%
2. 行业分类 + 宏观事件 wiki（每周更新）
3. 当前 ticker 近 90 天新闻摘要 + 财报摘要（每天更新一次）
4. 当前事件 + 即时行情（不缓存）

预期节省 40-60% 输入 token 成本。

---

## 信号→仓位映射

```
final_size = base_size × conviction × regime_weight × kelly_cap × risk_adj

base_size     = portfolio_equity × 5%（默认单票上限）
conviction    = judge 输出 0~1
regime_weight = macro_analyst 输出 0~1（VIX > 30 时收缩）
kelly_cap     = min(0.25, fractional_kelly(p_win, b))
risk_adj      = target_vol / asset_vol_60d
```

止损：RiskManager 强制 2×ATR stop，硬规则不经 LLM。

---

## 风控规则（确定性 Python，不交 LLM）

| 规则 | 阈值 |
|------|------|
| 单票仓位 | ≤ 5% NAV |
| 单行业 | ≤ 25% NAV |
| 最大回撤熔断 | -10% from peak → 全平 + 暂停 24h |
| 财报前 | 24h 不新开仓 |
| 流动性 | 日均成交额 > $10M |
| LLM 异常 | JSON 解析失败 → 当日跳过该 ticker |
| 最大杠杆 | 1.0（MVP 不加杠杆） |

---

## 目录结构

```
newsalpha/
├── pyproject.toml              # uv + ruff + mypy
├── docker-compose.yml          # postgres + qdrant + redis
├── .env.example
├── Makefile
│
├── configs/
│   ├── agents.yaml             # 模型路由 + 辩论模式
│   ├── risk.yaml               # 风控阈值
│   ├── universe.yaml           # 股票池（SP500 子集）
│   └── prompts/                # 提示词 markdown 模板
│
├── src/newsalpha/
│   ├── core/
│   │   ├── state.py            # TradingState TypedDict
│   │   ├── graph.py            # build_graph()
│   │   └── events.py
│   ├── agents/                 # 每个 agent 一个文件
│   ├── tools/                  # LLM function-call 工具
│   │   ├── news/               # finnhub, alpaca, edgar
│   │   ├── market/             # quote, bars
│   │   ├── ta/                 # indicators, patterns
│   │   └── memory/             # vector_search, reflect_log
│   ├── data/
│   │   ├── connectors/         # API 客户端（带 retry + rate limit）
│   │   └── storage/            # qdrant / postgres / duckdb 封装
│   ├── llm/
│   │   ├── client.py           # AnthropicClient + prompt caching
│   │   ├── routing.py          # per-agent 模型选择
│   │   └── budget.py           # 成本上限熔断
│   ├── memory/
│   │   ├── vector_store.py
│   │   ├── episodes.py
│   │   └── retrieval.py
│   ├── execution/
│   │   ├── broker.py           # AlpacaBroker (paper/live 开关)
│   │   └── sizing.py           # kelly / vol target
│   ├── risk/
│   │   └── rules.py            # 全部硬规则，无 LLM
│   ├── backtest/
│   │   ├── replay.py           # 决策快照回放
│   │   └── metrics.py          # sharpe / sortino / IR
│   └── api/                    # FastAPI + WebSocket
│
├── frontend/                   # W5 Streamlit → W6 Next.js
│
├── workers/
│   ├── news_listener.py        # Alpaca/Finnhub → Redis Streams
│   ├── decision_worker.py      # 消费事件 → LangGraph
│   └── reflection_worker.py   # 平仓后异步
│
└── tests/
    ├── unit/
    ├── integration/            # LLM 响应录制回放
    └── eval/                   # 50 个标注样本守门
```

---

## 开发里程碑（6 周）

### Week 1 — 基础设施
- 仓库初始化（uv / ruff / pre-commit）
- `docker-compose` 拉起 Postgres + Qdrant + Redis
- `AnthropicClient` 封装（prompt caching + cost 计量 + retry）
- 数据连接器：Finnhub、Alpaca、yfinance、FRED（各带 mock）
- LangGraph 骨架：State + dummy NewsCollector 跑通 END-to-END
- **交付**：`python -m newsalpha.demo` 输出标准化新闻对象

### Week 2 — 分析师层
- 4 个分析师 agent + 工具绑定
- Qdrant 向量库 + 新闻 embedding ingestion
- 提示词模板 + few-shot 样本
- 单元测试覆盖率 > 60%
- **交付**：给定 ticker + 新闻，输出 4 份 JSON 报告

### Week 3 — 辩论 + 决策（核心）
- Bull / Bear / Judge + 条件辩论边
- A/B 辩论机制（3 种模式可配置切换）
- Trader（Opus 4.7）+ RiskManager 硬规则
- LangSmith 集成，可视化完整 trace
- **交付**：一次完整决策 trace JSON + 截图

### Week 4 — 回测 + 记忆
- 决策快照写入 Postgres + Replay 引擎
- backtrader 集成，跑 2023 年 5 只股票
- Reflection agent + Qdrant 经验写入/检索
- quantstats 报告自动生成
- **交付**：首份回测 HTML 报告（Sharpe / MDD / 胜率）

### Week 5 — 执行 + 渐进扩展 + Streamlit Demo
- Alpaca paper trading 接通
- 加入 MacroAnalyst + PortfolioManager + ReflectionAgent（完整 12 个）
- FastAPI + WebSocket 推送
- **Streamlit dashboard**：新闻流 / 辩论过程 / 持仓 / 回测曲线
- 部署到 Fly.io / Railway
- **交付**：可分享 demo 链接

### Week 6 — 打磨 + Next.js 升级
- Next.js + React Flow 决策图谱页（每笔交易全链路可追溯）
- Debate Viewer 页（Bull/Bear 对话 UI + 论点引用卡片）
- 长回测（2020-2025，覆盖 5 种 regime）
- README + 架构文档 + 3 分钟 demo 视频
- **交付**：v1.0 生产原型，可作品集展示

---

## 验证方法

### 基准对照（同时跑 4 条）
1. SPY buy-and-hold（被动基准）
2. Finnhub sentiment 字段直接做多空（无 LLM 基准）
3. 单 agent LLM 直出信号（无辩论，证明多 agent 增量价值）
4. NewsAlpha 完整版

### 关键指标目标
| 指标 | 目标 |
|------|------|
| Sharpe (年化) | > 1.0 |
| Max Drawdown | > -15% |
| Alpha vs SPY | > 5% |
| Hit Rate | > 52% |
| 单次决策延迟 P95 | < 90s |
| LLM 成本/单笔 | < $1.5 |

### 回测窗口（多 regime 验证）
- 2020 H1：Covid 崩盘 + 反弹
- 2022：加息熊市（-20%）
- 2023：AI 牛市 + SVB 危机
- 2025 H1：OOS 验证

### 关键合规说明
- 默认 `BROKER_MODE=paper`，实盘需二次 CLI 确认 + HITL
- UI / README 显著免责："本系统为研究/演示用途，不构成投资建议"
- 不再分发 Benzinga/Finnhub 原始新闻文本

---

## 立即可执行的 Week 0 启动步骤

1. `uv init newsalpha && cd newsalpha`
2. 申请免费账号：Finnhub / Alpaca Paper / Anthropic / FRED / LangSmith
3. 编写 `docker-compose.yml`，一键拉起 Postgres + Qdrant + Redis
4. 建 `.env.example` 占位所有密钥
5. 跑通最小 LangGraph hello-world：`START → news_collector(mock) → END`
