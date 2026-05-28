# NewsAlpha — W4 阶段总结报告

> 主题：回测引擎 + 决策快照 Replay + Reflection 记忆
> 报告日期：2026-05-27
> 总工期：6 周 · 当前进度：4/6（67%）

---

## 1. W4 一览

| 子目标 | 主要交付 | 验收 |
|---|---|---|
| **W4-1** 决策快照 Replay | [replay.py](src/newsalpha/backtest/replay.py) — `replay_decision()` + `extract_signals_for_backtest()` | 5 测试覆盖 100% — 含风控配置 override 重放、损坏快照容错 |
| **W4-2** 回测引擎 | [engine.py](src/newsalpha/backtest/engine.py) — backtrader 集成 + 多 ticker 聚合 | 5 测试覆盖 84% — 端到端 22 笔 trades 跑通 |
| **W4-3** 性能指标 | [metrics.py](src/newsalpha/backtest/metrics.py) — Sharpe/Sortino/MDD/CAGR/Win-rate/Profit factor | 14 测试覆盖 95% |
| **W4-4** 报告生成 | [reports.py](src/newsalpha/backtest/reports.py) — quantstats HTML + Markdown 备选 | E2E：`backtest_*.md` + `metrics_*.json` |
| **W4-5** Reflection 记忆 | [memory/episodes.py](src/newsalpha/memory/episodes.py) + [agents/reflection.py](src/newsalpha/agents/reflection.py) | 8 测试覆盖 75% — 含 Qdrant 真接入 + 内存 fallback |
| **W4-6** Backtest CLI | [backtest/cli.py](src/newsalpha/backtest/cli.py) — `python -m newsalpha.backtest.cli` | 端到端跑通：3 ticker × 8 synth 信号 → 22 笔 → 报告 |

整体增量：**6 个新模块 / 4 个新测试文件 / 32 个新测试 / 81 个测试全绿**。

---

## 2. 差异化亮点 #2 完成体：决策快照 + Replay

### 2.1 设计目标

每次完整图运行的全量 state 落盘 → 任意时刻可"无成本"重跑下游：
- **风控参数 A/B**：改 `risk.yaml` 后 replay 历史决策，看哪些会被新规则拒绝
- **回测信号源**：扫所有 accepted 快照 → backtrader 信号流 → PnL
- **审计回放**：监管/复盘时还原任意历史决策的完整证据链

### 2.2 关键 API

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

### 2.3 关键决策

| 决策 | 理由 |
|---|---|
| **Replay 不重新调 LLM** | 信号、辩论、verdict 全部从快照取；只重跑 `risk.rules.evaluate_signal`（纯 Python，确定性）。这是项目"快照即真相"原则的具体兑现。 |
| **JSON-on-disk（W4）vs Postgres（W5+）** | W4 优先把回路打通；持久化层在 W5 接 Alpaca 时统一升级到 Postgres，避免双线返工。 |
| **损坏快照不阻断** | `extract_signals_for_backtest` 遇到坏 JSON 只 warn 不抛 — 一笔坏数据不能让整个回测炸 |

---

## 3. 回测引擎（backtrader）

### 3.1 拓扑

```
snapshots/                     ← 来源：W3 快照
   │
   ▼
extract_signals_for_backtest    ← 仅取 accepted
   │
   ▼
NewsAlphaStrategy(bt.Strategy)  ← 持有 pending_signals 队列
   │
   ▼
[每个交易日 next()]
   ├─ 检查止损 / 止盈
   ├─ 弹出 as_of ≤ today 的信号 → buy/sell
   │
   ▼
trade_log + portfolio_values + returns
   │
   ▼
metrics + Markdown report
```

### 3.2 关键设计选择

| 选择 | 替代方案 | 理由 |
|---|---|---|
| Pre-computed signals 输入策略 | 在策略内反向调 LangGraph 实时生成 | 保持回测**确定性**；LLM 调用昂贵且非确定，应在快照阶段固化 |
| `params.signals` 注入而非全局变量 | bt.Cerebro 默认 strategy class 全局 | 多 ticker 多 cerebro 实例并行时不会串信号 |
| `commission=0.001` 默认 | 0 / 真实 fee schedule | 1bps 是 Alpaca/IBKR 平均费率的合理近似；后续接真实 broker 时切换 |
| `get_default_market_connector` 走 mock-or-yfinance | 硬绑 yfinance | CI 与离线开发友好（沿用 W2 既有 connector 抽象） |

### 3.3 Strategy 实现要点

- **`stop()` 钩子**：回测结束时强平所有未平仓位，记录 `exit_reason="end_of_backtest"`，避免 PnL 漏统计
- **size_pct → shares 转换**：`int(portfolio_value * size_pct / price)` — 整数股，避免分数股错乱
- **side="long"|"short" 分支**：止损/止盈方向相反，用一个 `side` 字段统一处理

### 3.4 端到端验证

```
synth signals: 3 tickers × 8 = 24 input
mock OHLCV (deterministic seeded random walk)
→ 22 trades executed
→ Win rate 59.1%, Profit factor 1.54
→ 报告 + metrics JSON 落盘
```

---

## 4. 性能指标库

[metrics.py](src/newsalpha/backtest/metrics.py) — 纯 numpy/pandas，无外部依赖，95% 覆盖。

| 函数 | 用途 | 边界处理 |
|---|---|---|
| `sharpe_ratio(returns)` | 年化 Sharpe（√252） | std<1e-12 → 0；空 series → 0 |
| `sortino_ratio(returns)` | 下行波动率 Sharpe | 无下行波动 → ∞ 或 0 |
| `max_drawdown(returns)` | 峰值-谷值最大跌幅 | 空 → 0，否则 ≤ 0 |
| `cagr(returns)` | 复合年化收益 | 总收益 ≤ 0 → 0 |
| `win_rate(trades)` / `profit_factor(trades)` | 交易级胜率/盈亏比 | 全胜 → ∞；空 → 0 |
| `compute_all_metrics(...)` | 一次性算完整套 | 含基准 → 加 alpha_vs_benchmark |

**关键 bug 修复**：`pd.Series([0.001]*100).std()` 返回 ~1e-19（浮点精度），不是 0 —— Sharpe 飙到 7e16。改为 `std < 1e-12` 容差判断。

---

## 5. 差异化亮点 #3：Reflection 记忆

### 5.1 设计

```
平仓事件 (backtest 或实盘)
    │
    ▼
ReflectionAgent.reflect_on_trade()
    │ ├ 输入：trade_log entry + decision_state（分析师报告/辩论记录）
    │ ▼
    │ LLM (Sonnet 4.6) → {what_worked[], what_failed[], lessons[], key_signals[]}
    │
    ▼
Episode → text_summary → embed_text() → vector
    │
    ▼
write_episode() → Qdrant (or InMemoryEpisodeStore fallback)
    │
    ▼
[未来辩论]
retrieve_similar(query="AAPL bull earnings", ticker="AAPL", limit=3)
   → top-K 相似历史经验注入 Bull/Bear 上下文 (W5 接入)
```

### 5.2 Episode schema

```python
@dataclass
class Episode:
    ticker: str
    side: str
    entry_date: str
    exit_date: str
    pnl_pct: float
    conviction: float          # 入场时 judge 给的 conviction
    regime: str                # bull|bear|chop|crisis (W5 由 MacroAnalyst 标注)
    what_worked: list[str]     # 哪些信号正确
    what_failed: list[str]     # 哪些信号失败
    lessons: list[str]         # 可复用的教训
    key_signals: list[str]     # 决定性信号清单
    trace_id: str              # 链回原始决策快照
```

### 5.3 关键工程选择

| 选择 | 理由 |
|---|---|
| **Hash-based 占位 embedding** | W4 不引入 embedding API（避免依赖 Voyage/OpenAI/Anthropic embeddings 不一致）；后续切真实 embedding 只改 `embed_text()` 一个函数 |
| **InMemoryEpisodeStore fallback** | Qdrant 服务挂了不阻断工作流；环境变量 `NEWSALPHA_MEMORY_BACKEND=memory` 强制内存模式 |
| **`reflect_batch()` 不调 LLM** | 回测时百笔 trade 走 LLM 太贵；从 PnL 自动产 lessons 模板，"真实的" reflection 留给实盘事件 |
| **episode_id = md5(ticker\|entry\|exit\|trace_id\|created_at)** | 同一笔交易反思可重复写（覆盖最新版）；不同笔通过 trace_id 区分 |

---

## 6. Backtest CLI

[backtest/cli.py](src/newsalpha/backtest/cli.py) — 一站式入口。

```bash
# 用 W3 历史快照
uv run python -m newsalpha.backtest.cli --tickers AAPL,MSFT,NVDA --start 2023-01-02 --end 2023-12-29

# 无快照时合成 mock 信号（仍跑 backtrader 真实价格）
uv run python -m newsalpha.backtest.cli --tickers AAPL,MSFT,NVDA --synth
```

输出：
- `data/reports/backtest_{ts}.md` — 含 metrics 表格 + 交易明细
- `data/reports/metrics_{ts}.json` — 机器可读 KPI

实测：22 trades / 59.1% win rate / profit factor 1.54 / 端到端 < 1s（mock 数据）

---

## 7. 累计成果

| 项目 | W3 末 | W4 末 | 增量 |
|---|---|---|---|
| Python 模块 | 35 | 43 | +8 |
| 测试文件 | 11 | 14 | +3 |
| 测试数量 | 49 | 81 | +32 |
| 总覆盖率 | 85% | 77% | -8pp（新增大模块未全测） |
| 核心模块覆盖率 | — | engine 84% / replay 100% / metrics 95% / snapshots 100% | — |

### 7.1 12 智能体进度

| # | Agent | 状态 |
|---|---|---|
| 1 | NewsCollector | ✅ W1 |
| 2-4 | Sentiment / Fundamental / Technical | ✅ W2 |
| 5-7 | Bull / Bear / DebateJudge | ✅ W3 |
| 8 | Trader (Opus 4.7) | ✅ W3 |
| 9 | RiskManager（合并） | ✅ W3 |
| 10 | **ReflectionAgent** | ✅ **W4** |
| 11 | MacroAnalyst | ⏳ W5 |
| 12 | PortfolioManager | ⏳ W5 |

### 7.2 三大差异化亮点

| 亮点 | 状态 |
|---|---|
| ① A/B 辩论机制 | ✅ W3 |
| ② 决策快照回放 | ✅ **W4 完整体**（snapshot 写 + replay 读 + override + signal 提取） |
| ③ Reflection 记忆 | 🟡 **W4 写入完成**；W5 接入辩论上下文检索 |

---

## 8. 已知限制 & W5 路线

### 8.1 W4 留下的债

- `data/connectors/news.py` Finnhub 路径仍然 44% 覆盖（W2 留下，W4 没碰）
- `embed_text()` 是哈希占位 — 语义相似度没有真实意义；W5 切真 embedding 模型
- `reflect_batch()` 跳过 LLM，规则化生成 lessons —— 实盘 webhook 触发时走真实 LLM 路径
- backtest 滑点未建模（默认 0），仅有 commission 1bps —— 长回测时需补 slippage model

### 8.2 W5 路线

1. **AlpacaBroker** 接通 paper trading + `BROKER_MODE=live` 二次确认
2. **MacroAnalyst**（Sonnet 4.6）+ **PortfolioManager**（Opus 4.7）补全到 12 智能体
3. **FastAPI + WebSocket** 推送实时事件流
4. **Streamlit dashboard** — 新闻流 / 辩论过程 / 持仓 / 实时 PnL
5. Reflection 检索接入 Bull/Bear 上下文（注入 top-3 相似历史）

---

## 9. 进度判断

按 6 周计划，W4 末交付：
- ✅ Replay 引擎完整体（差异化 #2 兑现）
- ✅ backtrader 跑通端到端
- ✅ quantstats 报告（HTML + MD 双 fallback）
- ✅ Reflection 写入路径（差异化 #3 写入侧完成）
- 🟡 LangSmith 推迟到 W5（trace 价值在前端可视化时才显现）

**结论：W4 完整完成；进度符合预期，可按计划进入 W5。**
