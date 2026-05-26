# NewsAlpha — W1/W2/W3 阶段总结报告

> 项目：新闻舆情驱动的多智能体美股交易系统
> 框架：LangGraph + Anthropic Claude（Opus 4.7 / Sonnet 4.6 / Haiku 4.5）
> 报告日期：2026-05-27（W3 完成）
> 总工期：6 周 · 当前进度：3/6（50%）

---

## 1. 阶段一览

| 周 | 主题 | 关键交付 | 验收 |
|---|---|---|---|
| **W1** | 基础设施 + 骨架 | LangGraph END-to-end + Anthropic 客户端（缓存+成本+重试）+ Mock 数据连接器 | `python -m newsalpha.demo` 输出标准化新闻 |
| **W2** | 分析师层 | 3 个分析师（Sentiment/Fundamental/Technical）并行 fan-out + 真实数据连接器（yfinance/Finnhub）+ 纯 Python TA 库 | 给定 ticker 输出 3 份 JSON 报告 |
| **W3** | 辩论 + 决策核心 | Bull/Bear/Judge 多轮辩论 + Trader（Opus 4.7）+ 确定性 RiskManager + 决策快照持久化 | 49 测试全绿 / 85% 覆盖率 |

整体规模：47 个 Python 模块、7 个 prompt 模板、3 个 YAML 配置、3406 行（含测试）。

---

## 2. W1 — 基础设施与骨架（已完成）

### 2.1 工程基础

- 包管理：`uv` + `pyproject.toml`（[pyproject.toml](pyproject.toml)）
- Lint/Type：`ruff` + `mypy`，`pre-commit` 钩子
- 容器：[docker-compose.yml](docker-compose.yml) — Postgres 15 + Qdrant + Redis 一键起
- 配置：[.env.example](.env.example) 占位所有密钥；[Makefile](Makefile) 提供 `make demo`/`make test`

### 2.2 核心抽象

- **状态模型** [state.py](src/newsalpha/core/state.py) — `TradingState: TypedDict` + `NewsItem`/`MarketSnapshot` Pydantic 边界校验
- **LLM 客户端** [llm/client.py](src/newsalpha/llm/client.py) — Anthropic SDK 包装：
  - 提示缓存（`cache_control` 顶层断点，预期节省 40-60% input token）
  - 成本计量（按 model 单价 + cache hit/miss 分别计）
  - `tenacity` 重试（指数退避，3 次）
  - JSON 解析容错（`_try_parse_json` 兜底返回 `None`，不抛异常）
- **路由** [llm/routing.py](src/newsalpha/llm/routing.py) — per-agent 模型/参数从 [agents.yaml](configs/agents.yaml) 加载
- **预算守门** [llm/budget.py](src/newsalpha/llm/budget.py) — 日成本上限熔断，避免暴走

### 2.3 数据连接器（W1 全部 Mock）

- [news.py](src/newsalpha/data/connectors/news.py) — `MockNewsConnector` + 后续在 W2 加入的 `FinnhubNewsConnector`
- [market.py](src/newsalpha/data/connectors/market.py) — `MockMarketDataConnector` + W2 的 `YFinanceMarketDataConnector`

### 2.4 关键决策

| 决策 | 理由 |
|---|---|
| TypedDict 而非 BaseModel 做 State | LangGraph 原生支持 reducer，`Annotated[..., add]` 才能走并行合并 |
| 三层 prompt 缓存断点 | system / 行业知识 / 当日 ticker 摘要 — 命中率分层最大化 |
| Mock 优先 | 测试可在无 API key 离线跑，CI 友好 |

---

## 3. W2 — 分析师层（已完成）

### 3.1 三个分析师节点

| Agent | 模型 | 职责 | 输出 schema 关键字段 |
|---|---|---|---|
| `sentiment_analyst` | Sonnet 4.6 | 读 news + market_snapshot 评极性 | `polarity ∈ [-1,1]`, `confidence`, `horizon` |
| `fundamental_analyst` | Sonnet 4.6 | 5 维基本面打分（增长/利润/现金/杠杆/估值）；无信息时保持 5.0 中性 | `scores`, `event_driven`, `citations` |
| `technical_analyst` | Sonnet 4.6 | **解释**确定性指标面板（不计算） | `signals[]`, `overall_bias`, `panel`（透传） |

### 3.2 TA 工具层（纯 Python，零原生依赖）

[tools/ta/indicators.py](src/newsalpha/tools/ta/indicators.py) — RSI / EMA / MACD / ATR / VWAP / 朴素 S/R / `summarize()` 一站式面板。

**关键修复**：RSI 在纯单边行情下分母为 0，会级联出 NaN。改用四个 `where` 条件覆盖：
- `loss==0 & gain>0` → 100（纯涨）
- `gain==0 & loss>0` → 0（纯跌）
- 双 0 → 50（平盘）
- 正常情况标准公式

### 3.3 LangGraph 并行 fan-out

```
START → news_collector
        ↓ (fan-out)
  sentiment_analyst | fundamental_analyst | technical_analyst
        ↓ (fan-in)
   analysts_ready → END
```

- 三个分析师写入**不相交**的 state slot（避免合并冲突）
- `cost_usd: Annotated[float, add]` 启用 reducer 累加并行成本写入

### 3.4 关键决策

| 决策 | 理由 |
|---|---|
| 系统 prompt 改用 Markdown 文件 | 便于版本对比、PR review、A/B 实验只改文件不改代码 |
| 技术面板**先确定性计算再交给 LLM 解释** | 数字算错代价高，叙事写错代价低；分工最大化两者长板 |
| Opus 4.7 不传 `temperature` | 通过 `NO_SAMPLING_PARAMS = {"claude-opus-4-7"}` 在 client 层条件透传 |

### 3.5 W2 验收

- 27 个测试 / 82% 覆盖率
- 集成测试：mock 三个 LLM，跑通完整图，断言 `cost_usd >= 0.003`

---

## 4. W3 — 辩论 + 决策核心（已完成，差异化亮点 #1）

这是项目相比 [TradingAgents](https://arxiv.org/abs/2412.20138) 的**第一大差异化点**：A/B 可切换的辩论机制。

### 4.1 辩论编排

```
analysts_ready → debate_orchestrator → bull_researcher → bear_researcher → round_advancer
                                            ↑                                    ↓ (条件边)
                                            └──── continue（round ≤ N） ←────────┘
                                                       ↓ (round > N)
                                                   debate_judge
                                                       ↓ (条件边)
                                              conviction ≥ 0.6 → trader → risk_manager → END
                                              conviction < 0.6 → log_only → END
```

**3 种可切换的辩论模式**（仅改 [agents.yaml](configs/agents.yaml) 的 `debate.mode`，图结构不变）：

- **adversarial** — Bull 立论，Bear 必须按 id 引用并反驳（默认）
- **panel** — 双方独立陈述，Judge 综合
- **socratic** — Judge 出引导问题，双方先回答再展开

切换零成本意味着可以做 A/B 对比研究：哪种机制在哪类事件上决策准确率更高。

### 4.2 角色与契约

| Agent | 模型 | 输入要点 | 关键输出字段 |
|---|---|---|---|
| `bull_researcher` | Sonnet 4.6 (T=0.4) | 分析师面板 + 历史轮论点 | `claims[]`（每条必引证据 id）+ `conviction` |
| `bear_researcher` | Sonnet 4.6 (T=0.4) | 同上 + 区分 *risk* 与 *thesis* | `claims[]` + `rebuts_bull_id` |
| `debate_judge` | Sonnet 4.6 (T=0.1) | 完整辩论记录 | `winner`/`directional_bias`/`conviction`/5 维评分 rubric |
| `trader` | **Opus 4.7** | judge 裁决 + 分析师 + 持仓上下文 | `action`/`size`/`stop`/`take_profit` |

`bull_arguments` 和 `bear_arguments` 用 `Annotated[list, add]` 做 append-only，多轮自然累积。

### 4.3 Trader 短路：节省成本 + 风险姿态对齐

[trader.py](src/newsalpha/agents/trader.py) — 当 `judge_verdict.conviction < 0.6` 或 `bias == "neutral"` 时**直接返回 `hold` 而不发起 LLM 调用**。这同时实现两个目标：
1. **省 token** — 弱信号下不浪费 Opus 调用（约 $0.03/次）
2. **风控姿态** — 系统级偏好"少错过不如少错"，与项目 README 的免责声明一致

### 4.4 RiskManager — LLM 与真金白银的信任边界

[risk/rules.py](src/newsalpha/risk/rules.py) — **纯 Python，永不调 LLM**。规则按顺序应用：

| 规则 | 行为 | 配置项 |
|---|---|---|
| `hold` 短路 | 拒绝 + reason `trader_recommended_hold` | — |
| 单票上限 5% NAV | clamp 而非拒绝 + `size_capped` 告警 | `position.max_single_pct` |
| 强制止损 | 缺失时按 2×ATR(14) 回填 | `stops.atr_multiplier` |
| Long stop ≥ entry | 拒绝 | — |
| Short stop ≤ entry | 拒绝 | — |
| 流动性 < $10M | 拒绝 | `universe_filter.min_avg_dollar_volume_usd` |
| 持仓总和超 cap | clamp 到剩余 headroom | — |

每次决策返回 `RiskDecision` 含 `accepted`/`reasons[]`/`adjustments[]`/`rule_versions{}` —— 全量审计可回放。

### 4.5 决策快照（差异化亮点 #2 雏形）

[backtest/snapshots.py](src/newsalpha/backtest/snapshots.py) — 每次完整图运行落盘 JSON，包含全 state（含 `bull_arguments` / `bear_arguments` / `judge_verdict` / `risk_decision`）。W4 将扩展为 Postgres + 节点级输入/输出/原始 LLM 响应记录，支持"只替换 Bull prompt 后从快照重跑下游"的提示词消融实验。

### 4.6 W3 验收

- **49 测试全绿**（`test_debate_and_decision.py` 17 个 + `test_graph_w3.py` 2 个 + `test_snapshots.py` 4 个 + 既有 26 个）
- **85% 覆盖率**（demo.py 不计入则 ~89%）
- 端到端断言：高 conviction → 完整下单链；低 conviction → `log_only` 分支 + 断言 Trader 未被调用

---

## 5. 累计成果

### 5.1 完成度

| 计划项 | 状态 |
|---|---|
| LangGraph END-to-end 骨架 | ✅ W1 |
| Anthropic 客户端（缓存+成本+重试） | ✅ W1 |
| 4 个数据连接器（Finnhub/Alpaca/yfinance/FRED） | 🟡 yfinance + Finnhub 已接，Alpaca/FRED W4-5 |
| 4 个分析师 | 🟡 3/4（Macro 推迟 W5，按计划） |
| Bull/Bear/Judge 多轮辩论 + 3 种 A/B 模式 | ✅ W3 |
| Trader (Opus 4.7) + RiskManager 硬规则 | ✅ W3 |
| LangSmith 集成 | ⏳ W4 |
| 决策快照 + Replay 引擎 | 🟡 快照写入完成，Replay W4 |
| Reflection 记忆 | ⏳ W5 |
| 回测 + quantstats 报告 | ⏳ W4 |
| Streamlit demo | ⏳ W5 |
| Next.js 决策图谱 | ⏳ W6 |

### 5.2 测试与质量

- **49/49 测试通过**，覆盖单元 + 集成 + mock-based 端到端
- **85% 覆盖率**（目标 >60%）
- 核心模块达 100%：state / graph / config / 6 个 agent 节点 / snapshots
- Risk rules 74%（部分边缘 reason 路径未走完，W4 补）

### 5.3 关键架构权衡（已沉淀）

1. **LLM 算解释，Python 算数字** — TA 指标 / 风控规则全确定性，LLM 只做叙事性判断
2. **A/B 通过 prompt + config 实现，不动图结构** — 切换辩论机制只改 yaml，复用一份 LangGraph
3. **Trader 短路 + RiskManager 硬卡** — 在两个不同层面表达"宁错过不错杀"的风险姿态
4. **快照即真相** — 每次决策的全量 state 落盘，是回放 / 复盘 / Reflection 的唯一来源

---

## 6. 已知风险与待办

### 6.1 技术债

- `data/connectors/news.py` Finnhub 路径覆盖率 49% — 需要在 W4 补带 fixture 的集成测试
- `risk/rules.py` 多条 reason 路径未被测试覆盖（headroom clamp / 流动性拒绝），W4 补
- `demo.py` 0% 覆盖率（CLI 入口，靠手动验证），可加 smoke test

### 6.2 W4 路线（下一周）

1. backtrader 集成 + 从 snapshot 回放决策（Replay 引擎，**差异化亮点 #2 完整体**）
2. ReflectionAgent + Qdrant `episodes` collection（**差异化亮点 #3**）
3. quantstats 自动报告：Sharpe / MDD / Hit Rate / Alpha vs SPY
4. 跑 2023 年 5 只代表股，产出首份回测 HTML

### 6.3 合规与安全

- 默认 `BROKER_MODE=paper` 已在 [config.py](src/newsalpha/core/config.py) 强制
- Live 模式需 CLI 二次确认 + HITL（W5 接 Alpaca 时实施）
- 不再分发 Benzinga/Finnhub 原始新闻文本（在 README 显著标注）
- UI / README 免责声明："本系统为研究/演示用途，不构成投资建议"

---

## 7. 进度判断

按 6 周计划，W3 末应交付完整决策路径 + LangSmith trace。当前：
- ✅ 决策路径完整（49 测试为证）
- 🟡 LangSmith 推迟到 W4 与 backtrader 一起做（不影响主路径）
- ✅ A/B 辩论机制已落地（差异化 #1 完成）

**结论：进度符合预期，质量略超预期**（覆盖率目标 60%，实际 85%）。可按计划进入 W4。
