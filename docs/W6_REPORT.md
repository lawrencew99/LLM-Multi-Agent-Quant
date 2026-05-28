# NewsAlpha — W6 阶段总结报告（v1.0 收官）

> 主题：长回测 2020-2025 + 决策图谱可视化 + 文档打磨 + v1.0
> 报告日期：2026-05-27
> 总工期：6 周 · 当前进度：6/6（**100% 完成 🎉**）

---

## 1. W6 一览

| 子目标 | 主要交付 | 验收 |
|---|---|---|
| **W6-1** 长回测 2020-2025 | [long_backtest.py](src/newsalpha/backtest/long_backtest.py) — 4 regime 段 + regime-aware 信号生成 | 6 测试 / 端到端跑通 8 ticker × 4 segments × 360 信号 → 305 trades |
| **W6-2** 决策图谱可视化 | [decision_graph.py](src/newsalpha/dashboard/decision_graph.py) — Sankey + Bar + Pie + Histogram + Box | 9 测试 / Streamlit 新增 "Decision Graph" 页面 |
| **W6-3** 文档 / Makefile / v1.0 | README 重写 + [architecture.md](docs/architecture.md) + Makefile 扩展 | 5 个新 make targets：`backtest`, `long-backtest`, `api`, `dashboard` |
| **W6-4** 全面测试 + 报告 | 全套 123 测试全绿 + 本报告 | 0 regression / 27 个 W4-W6 期间新增测试 |

整体增量：**2 个新模块 / 2 个新测试文件 / 15 个新测试 / 文档/Makefile/README 重写**。

---

## 2. 长回测 2020-2025

### 2.1 4 个 Regime 段设计

| 段 | 时间 | Regime | 长偏 | conviction 范围 | size 范围 | 信号/票 |
|---|---|---|---|---|---|---|
| `covid_crisis` | 2020-02 → 2020-06 | crisis | 0.30 | 0.55-0.75 | 0.01-0.03 | 8 |
| `bull_2021` | 2021-01 → 2021-12 | bull | 0.80 | 0.70-0.95 | 0.03-0.05 | 12 |
| `bear_2022` | 2022-01 → 2022-12 | bear | 0.35 | 0.60-0.80 | 0.02-0.04 | 10 |
| `recovery_2023_24` | 2023-01 → 2024-12 | bull | 0.70 | 0.65-0.90 | 0.03-0.05 | 15 |

### 2.2 设计意图

不直接调 LLM 跑 5 年（成本不切实际），而是通过 **regime 校准的合成信号** 模拟"如果系统真在那段历史中运行，理论行为会怎样"：
- 危机期：长偏 30%，小尺寸，低 conviction → 防御姿态
- 牛市期：长偏 80%，大尺寸，高 conviction → 进攻姿态
- 熊市期：长偏 35%，平衡多空 → 中性姿态
- 恢复期：长偏 70%，逐步加大 → 渐进进攻

### 2.3 端到端验证

Mock 数据下跑通：
- 8 ticker × 4 segments × 平均 11 信号/票 = **360 信号**
- 实际成交 **305 trades**（其余因 stop/tp 价位与合成价格不匹配未触发）
- 4 段 + 全期 metrics 全部输出
- 自动对比报告：`long_backtest_<ts>.md` + `metrics_long_<ts>.json`

### 2.4 输出报告示例

```
┌────────┬──────────────────┬──────────────────────────┬────────┬───────┬───────┐
│ regime │ name             │ period                   │ Sharpe │ MDD%  │ Trades│
├────────┼──────────────────┼──────────────────────────┼────────┼───────┼───────┤
│ crisis │ covid_crisis     │ 2020-02-01 → 2020-06-30  │  1.17  │ -0.03 │  49   │
│ bull   │ bull_2021        │ 2021-01-01 → 2021-12-31  │ -0.57  │ -0.07 │  86   │
│ bear   │ bear_2022        │ 2022-01-01 → 2022-12-31  │ -1.47  │ -0.07 │  69   │
│ bull   │ recovery_2023_24 │ 2023-01-01 → 2024-12-31  │ -0.27  │ -0.22 │ 101   │
└────────┴──────────────────┴──────────────────────────┴────────┴───────┴───────┘
```

> 注：mock 数据下指标接近零属预期（合成价格 = 随机游走 + 合成信号无真 alpha）；切真 yfinance 数据可获得有意义对比。

---

## 3. 决策图谱可视化

### 3.1 5 种图

| 图 | 用途 | Plotly 类型 |
|---|---|---|
| **Sankey** | 信号流：Total → Bias → Conviction → Risk → Exec | go.Sankey |
| **Throughput Bar** | 每个 agent 接收到的信号数 | go.Bar |
| **Conviction Histogram** | All vs Accepted conviction 分布 | go.Histogram (overlay) |
| **Regime Pie** | 决策按 macro regime 的分布 | go.Pie |
| **Latency Box** | per-node 延迟箱线图 | go.Box |

### 3.2 Streamlit 集成

新增 "Decision Graph" 页面（dashboard 第二项），布局：
```
┌─────────────────────────────────────────────────┐
│              Sankey (signal flow)                │
└─────────────────────────────────────────────────┘
┌──────────────────────┬──────────────────────────┐
│   Throughput Bar     │     Regime Pie           │
└──────────────────────┴──────────────────────────┘
┌─────────────────────────────────────────────────┐
│         Conviction Distribution                  │
└─────────────────────────────────────────────────┘
```

### 3.3 鲁棒性

所有 5 个 builder 函数：
- 空快照 → 返回 "No data" 占位图（不抛异常）
- 部分管道 state（如只走到 sentiment_report 就中断）→ 正确递减计数
- 缺失 latency 数据 → 显示提示信息

---

## 4. 文档与 v1.0 打磨

### 4.1 README 重写

从"W3 完成快照"升级为 v1.0 完整体：
- 12 智能体表（含模型路由）
- 完整数据流图（包含 MacroAnalyst 第 4 路 + PortfolioManager 第 2 信任边界）
- Sizing pipeline 公式可视化
- Quick start 9 步（含 backtest + long-backtest + api + dashboard）
- 关键设计决策表扩展到 8 条

### 4.2 新增 architecture.md

5 层架构图 + LangGraph 状态定义 + 模型路由 + 辩论模式表 + backtest 管道 + 完整目录布局。这是给未来的协作者/招聘官的一站式技术索引。

### 4.3 Makefile 扩展

新增 5 个 target：
```
make backtest         # 合成信号一年回测
make long-backtest    # 2020-2025 4 段
make api              # uvicorn 启服务
make dashboard        # streamlit 启 UI
make test             # 全套 123 测试
```

---

## 5. v1.0 累计成果

| 项目 | W3 末 | W4 末 | W5 末 | **v1.0** |
|---|---|---|---|---|
| Python 模块 | 35 | 43 | 52 | **54** |
| 测试文件 | 11 | 14 | 17 | **19** |
| 测试数量 | 49 | 81 | 108 | **123** |
| 文档 | 1 | 2 | 3 | **5**（含 architecture） |
| 智能体 | 9 | 10 | 12 | **12**（闭合） |
| Streamlit 页面 | 0 | 0 | 5 | **6** |
| 命令行入口 | 1 | 2 | 4 | **5** |

### 5.1 12 智能体最终状态

| # | Agent | 模型 | 引入周 |
|---|---|---|---|
| 1 | NewsCollector | Haiku 4.5 | W1 |
| 2-4 | Sentiment / Fundamental / Technical | Sonnet 4.6 | W2 |
| 5-7 | Bull / Bear / DebateJudge | Sonnet 4.6 | W3 |
| 8 | Trader | **Opus 4.7** | W3 |
| 9 | RiskManager | (Pure Python) | W3 |
| 10 | ReflectionAgent | Sonnet 4.6 | W4 |
| 11 | MacroAnalyst | Sonnet 4.6 | W5 |
| 12 | PortfolioManager | (Pure Python) | W5 |

### 5.2 三大差异化亮点最终交付

| 亮点 | v1.0 状态 |
|---|---|
| ① **A/B 辩论机制** | ✅ adversarial / panel / socratic 三模式可配置切换（W3 完成） |
| ② **决策快照回放** | ✅ 写入 + replay + override + signal 提取 + Dashboard A/B 对比 UI（W3-W5 完整体） |
| ③ **Reflection 记忆** | ✅ 平仓后规则化/LLM 反思 + Qdrant/InMemory + Dashboard Memory 页面（W4-W5 完整体） |

---

## 6. v1.0 已知限制

### 6.1 规模/真实数据
- 长回测在 mock 模式验证管道；**真实 yfinance 数据下需重新跑**才能获得有意义指标
- AlpacaBroker live mode 未在 CI 测试 —— 需 paper 账号凭证（broker.py 当前 63% 覆盖率）
- LangSmith trace 推迟到生产部署阶段

### 6.2 工程债（v1.x 路线）
- `embed_text()` 仍为 SHA256 哈希占位 —— 切真 embedding 模型（如 voyage-2）后才有真正语义检索
- FastAPI 无鉴权 —— 本地/研究无碍，部署前需补 JWT/API-key
- Dashboard 未直接订阅 WebSocket —— 当前为页面刷新模式，需补 streamlit-extras 推送
- Reflection 检索未注入 Bull/Bear 上下文 —— 写入侧 OK，读取侧待 v1.1
- Backtest slippage 模型未建 —— 仅有 commission 0.001（10bps 双边可接受）

### 6.3 模型/数据债
- News connector Finnhub 路径 44% 覆盖（W2 留下，W4-W6 未碰）
- 长回测合成信号不依赖真新闻 —— 真闭环需历史新闻流（订阅 Finnhub 历史 API）
- TA 指标默认参数 —— 没做参数优化（避免过拟合，但实盘前需做 walk-forward）

---

## 7. 项目自评

### 7.1 招聘场景的差异化讲法

| 维度 | 我们的做法 | 区别于市面常见项目 |
|---|---|---|
| **Agent 架构** | 12 个 LangGraph 节点，并行 fan-out + 迭代辩论 + 双信任边界 | ≠ 单 prompt + 工具调用循环 |
| **回测** | 决策快照 → 信号 → backtrader → quantstats，Replay 不重调 LLM | ≠ 直接喂历史价格让 LLM"假装"决策 |
| **风控** | 100% 纯 Python 规则，可单测、可回放、可审计 | ≠ "让 LLM 评估风险"或纯 vibe-check |
| **存储** | TypedDict 全量快照 + Qdrant episode 记忆 + 决策日志 | ≠ 只存 final order |
| **可视化** | 5 种 Plotly 图 + Sankey 信号流 + A/B Replay UI | ≠ 仅打印日志 |
| **安全** | paper-mode 默认 + live 双重确认 + LLM 日预算熔断 + 信任边界 | ≠ "demo 跑通就好" |

### 7.2 完成度判断

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

---

## 8. 后续 v1.x 路线（可选）

| 版本 | 主题 | 预计工时 |
|---|---|---|
| v1.1 | 真 yfinance 长回测 + Voyage-2 embedding + Reflection 注入 | 1 周 |
| v1.2 | LangSmith trace + Prometheus metrics + 报警 | 1 周 |
| v1.3 | Walk-forward TA 参数优化 + slippage model | 1 周 |
| v1.4 | Next.js 决策图谱（替代 Streamlit） + Vercel 部署 | 2 周 |

---

## 致谢与项目回顾

6 周内交付：
- **54 个 Python 模块** (~5,400 行)
- **123 个单元测试**（全绿）
- **5 篇阶段报告 + 1 篇架构文档**
- **12 个 Claude 智能体**（Opus + Sonnet + Haiku 三层路由）
- **5 个对外接口**（CLI / FastAPI / WebSocket / Streamlit / 直接 Python API）

这是一个面向招聘场景的"能跑、能讲、能审"的多智能体量化交易系统 demo。**所有代码可在 mock 模式离线运行**，零 API 成本即可演示完整闭环。
