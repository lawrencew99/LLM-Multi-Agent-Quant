# NewsAlpha

新闻舆情驱动的多智能体美股交易系统。基于 **LangGraph** 编排 Anthropic Claude 智能体（Opus 4.7 决策 / Sonnet 4.6 分析 / Haiku 4.5 采集），从实时新闻事件触发，经多轮 Bull/Bear 辩论后由 Trader + 风控决策，通过 Alpaca paper trading 执行。

## 项目状态

| 阶段 | 主题 | 状态 |
|---|---|---|
| W1 | 基础设施 + LangGraph 骨架 | ✅ 完成 |
| W2 | 三分析师并行 fan-out + TA 工具层 | ✅ 完成 |
| W3 | Bull/Bear/Judge 辩论 + Trader + RiskManager | ✅ 完成 |
| W4 | 回测引擎 + Reflection 记忆 + quantstats | ⏳ 进行中 |
| W5 | 执行层 + Streamlit demo + 12 智能体补全 | ⏳ |
| W6 | Next.js 决策图谱 + 长回测 + v1.0 | ⏳ |

**当前规模**：47 个 Python 模块、7 个 prompt 模板、49 个测试全绿、覆盖率 85%。完整阶段总结见 [`docs/W1-W3_REPORT.md`](docs/W1-W3_REPORT.md)。

## 三大差异化亮点

1. **A/B 辩论机制** — `adversarial / panel / socratic` 三种模式可配置切换，仅改 [`configs/agents.yaml`](configs/agents.yaml) 不动图结构（W3 已交付）
2. **决策快照回放** — 每次图运行的全量 state 持久化为 JSON，支持只替换某 agent prompt 后从快照重跑下游做消融实验（W3 快照写入完成，W4 接入 Replay）
3. **Reflection 记忆** — 平仓后异步反思写入 Qdrant，辩论时检索相似历史案例注入 Bull/Bear 上下文（W5 交付）

## 系统架构

```
新闻 WebHook / 定时轮询 (Finnhub + Alpaca + SEC EDGAR)
         │
   NewsCollector (Haiku 4.5)
         │
   ┌─────┴─────┬───────────┐
   ▼           ▼           ▼
Sentiment  Fundamental  Technical    ← 并行 fan-out
(Sonnet)   (Sonnet)     (Sonnet)
   └─────┬─────┴───────────┘
         ▼
  BullResearcher ⇄ BearResearcher    ← 多轮辩论（A/B 可配置机制）
         │
    DebateJudge (Sonnet)
         │
   conviction < 0.6 → log_only → END
   conviction ≥ 0.6
         ▼
     Trader (Opus 4.7)
         ▼
   RiskManager (确定性 Python，无 LLM)  ← 信任边界
         │
   rejected → END        accepted → final_orders → END
```

详见 [`src/newsalpha/core/graph.py`](src/newsalpha/core/graph.py)。

## 快速开始

```bash
# 1. 安装依赖
uv sync --extra dev --extra ui

# 2. 启动后端服务（Postgres + Qdrant + Redis）
make up   # 等价于 docker compose up -d

# 3. 配置密钥（最少需要 ANTHROPIC_API_KEY）
cp .env.example .env

# 4. 跑通 hello-world demo
make demo

# 5. 运行测试套件
make test
```

无 API key 时，全部测试与 demo 可在 Mock 数据下离线运行 —— 在 `.env` 设置 `NEWSALPHA_MOCK_DATA=1`。

## 关键设计决策

| 决策 | 理由 |
|---|---|
| **TypedDict + `Annotated[..., add]` 状态** | LangGraph 原生 reducer，并行 fan-out 才能合并多个 agent 的成本/参数写入 |
| **数字算 Python，叙事算 LLM** | TA 指标 / 风控规则全确定性；LLM 只解释，不计算 |
| **辩论模式 A/B 通过 prompt + config 切换** | 复用同一 LangGraph 拓扑，研究三种机制对决策准确率的差异 |
| **Trader 在低 conviction 时短路 hold** | 弱信号下不发起 Opus 调用 — 既省 token 又对齐"宁错过不错杀"风险姿态 |
| **RiskManager 永不调用 LLM** | LLM 判断与真金白银的信任边界；硬规则可审计可回放 |
| **每次决策落盘全量 state** | 快照即真相，是回放 / 复盘 / Reflection 的唯一数据源 |

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

实现见 [`src/newsalpha/risk/rules.py`](src/newsalpha/risk/rules.py)。

## 目录结构

```
newsalpha/
├── configs/
│   ├── agents.yaml          # per-agent 模型路由 + 辩论模式
│   ├── risk.yaml            # 风控阈值
│   ├── universe.yaml        # 股票池
│   └── prompts/system/      # 7 个 agent 的 markdown 提示词
├── src/newsalpha/
│   ├── core/                # state / graph / config
│   ├── agents/              # 9 个 agent 节点
│   ├── llm/                 # client / routing / budget
│   ├── tools/ta/            # 纯 Python 技术指标
│   ├── data/connectors/     # finnhub / yfinance / mock
│   ├── risk/                # 确定性硬规则
│   ├── backtest/            # 决策快照（W4 接 backtrader）
│   └── memory/              # Qdrant 经验库（W5）
├── tests/unit/              # 49 个测试，85% 覆盖
└── docs/W1-W3_REPORT.md     # 阶段总结报告
```

## 技术栈

- **框架** — LangGraph (Python) · Anthropic SDK · pydantic + pydantic-settings · structlog · tenacity
- **数据** — yfinance (历史日线) · Finnhub (新闻+实时报价) · Alpaca (执行+流式新闻，W5) · FRED (宏观，W5)
- **存储** — Postgres (决策日志) · Qdrant (向量记忆) · DuckDB+Parquet (时序) · Redis Streams (事件总线)
- **回测/前端** — backtrader · quantstats · Streamlit (W5) → Next.js + React Flow (W6)
- **工具链** — uv · ruff · mypy · pytest · pre-commit

## 免责声明

本系统为**研究 / 演示用途**，所有信号与回测结果不构成投资建议。美股交易具有重大风险，使用者自担后果。系统默认运行于 Alpaca **paper trading** 模式（`BROKER_MODE=paper`），实盘需显式开关 + CLI 二次确认 + 人工 HITL。

不再分发 Benzinga / Finnhub 原始新闻文本 — 仅在内存中处理后保留摘要与 event_id。
