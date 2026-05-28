# NewsAlpha — W5 阶段总结报告

> 主题：执行层 + MacroAnalyst + PortfolioManager + FastAPI + Dashboard
> 报告日期：2026-05-27
> 总工期：6 周 · 当前进度：5/6（83%）

---

## 1. W5 一览

| 子目标 | 主要交付 | 验收 |
|---|---|---|
| **W5-1** AlpacaBroker 执行层 | [broker.py](src/newsalpha/execution/broker.py) — BaseBroker ABC + MockBroker + AlpacaBroker（paper/live）+ 安全开关 | 6 测试 · broker 63% / sizing 100% |
| **W5-2** 高级 Sizing | [sizing.py](src/newsalpha/execution/sizing.py) — Kelly 半分数 + 波动率目标 + conviction 缩放 + audit 分解 | 10 测试覆盖 100% |
| **W5-3** MacroAnalyst | [macro_analyst.py](src/newsalpha/agents/macro_analyst.py) — VIX/yield/trend → regime + LLM 增强 + heuristic fallback | 5 测试覆盖 98% |
| **W5-4** PortfolioManager | [portfolio_manager.py](src/newsalpha/agents/portfolio_manager.py) — regime_weight × conviction × size → final 下单 + audit trail | 4 测试覆盖 100% |
| **W5-5** FastAPI + WebSocket | [api/app.py](src/newsalpha/api/app.py) — REST + WS `/ws/events` + EventBus 推送 | 手动验证：`/health`, `/snapshots`, `/run` |
| **W5-6** Streamlit Dashboard | [dashboard/app.py](src/newsalpha/dashboard/app.py) — 5 页：Decisions / Debate / Backtest / Memory / Replay A/B | 手动验证 |
| **W5-7** 图拓扑升级 | [graph.py](src/newsalpha/core/graph.py) 更新 — macro_analyst 并行扇出 + portfolio_manager 最终节点 | 2 端到端测试 |

整体增量：**7 个新模块 / 3 个新测试文件 / 27 个新测试 / 108 个测试全绿**。

---

## 2. 执行层架构

### 2.1 Broker 层设计

```
BaseBroker (ABC)
├── MockBroker          ← 内存确定性，测试+回测
└── AlpacaBroker        ← alpaca-py SDK，paper/live
    └── confirm_live=True 才允许 BROKER_MODE=live
```

**安全措施：**
- `get_default_broker()` 工厂：`NEWSALPHA_BROKER=mock|alpaca`
- `AlpacaBroker(confirm_live=False)` + `BROKER_MODE=live` → `RuntimeError`
- 默认永远是 paper mode
- MockBroker 完整模拟：持仓管理 + 现金扣减 + order log

### 2.2 Sizing Pipeline

```
base_size_pct
    │
    ├── fractional_kelly(p_win, win_loss_ratio, fraction=0.25)
    │       └── 负 edge → 0
    ├── vol_target_size(base, asset_vol, target_vol=0.15)
    │       └── clip to [0.25×, 1.5×]
    ├── conviction_scaled_size(base, conviction, threshold=0.6)
    │       └── conviction < 0.6 → 0
    │
    ▼
compute_final_size() → min(kelly × vol × conviction × base, max_single_pct=0.05)
    │
    ▼
audit breakdown: {final_size_pct, kelly_factor, vol_factor, conviction_factor, capped}
```

---

## 3. MacroAnalyst — 12 智能体补全

### 3.1 工作流

1. 获取宏观面板：VIX（现值 + 5日均/20日均）、yield curve slope、SPY 50/200 DMA 比值
2. `_heuristic_regime(panel)` → 规则分类：

| 条件 | Regime | Weight |
|---|---|---|
| VIX > 35 | crisis | 0.3 |
| VIX < 20 + 50DMA > 200DMA | bull | 1.0 |
| yield slope < -0.2 OR 50DMA < 200DMA | bear | 0.6 |
| otherwise | chop | 0.75 |

3. LLM call（Sonnet 4.6）增强 → 覆盖 heuristic（若 LLM 可用）
4. 失败 fallback：heuristic 结果 + 记录 error → 管道不中断

### 3.2 输出

```python
{
    "macro_context": {"vix": 18.5, "yield_curve_slope_pct": 0.3, "spy_50dma_vs_200dma": 1.02},
    "macro_report": {"regime": "bull", "regime_weight": 1.0, "panel": {...}},
}
```

`regime_weight` 直接乘入 PortfolioManager 仓位计算。

---

## 4. PortfolioManager — 信任边界最终关卡

设计原则：**纯 Python，永不调 LLM**（同 RiskManager）。

### 4.1 逻辑

```python
final_size = min(
    raw_size × regime_weight × conviction,
    MAX_SINGLE_PCT  # 0.05
)
```

### 4.2 输出

- 修改 `final_orders[].size_pct` → 实际下单尺寸
- 写入 `portfolio_decision`:
  - `regime` / `regime_weight`
  - `audit[]`: 每笔订单的 `sizing_breakdown`（原始尺寸 → 各因子 → 最终尺寸）

### 4.3 Graph 拓扑

```
                trigger
                   │
              news_collector
                   │
         ┌─────────┼─────────┐
   fundamental  technical  sentiment  macro_analyst  ← 并行扇出(W5新增)
         └─────────┼─────────┘
              bull_researcher
              bear_researcher
              debate_judge
              trader
              risk_manager
              portfolio_manager  ← W5 新增（risk_manager 之后）
                   │
                  END
```

---

## 5. FastAPI + WebSocket

### 5.1 端点

| Method | Path | 功能 |
|---|---|---|
| GET | `/health` | 健康检查 |
| GET | `/snapshots` | 列出所有决策快照 |
| GET | `/snapshots/{id}` | 获取单个快照 |
| POST | `/decisions/replay` | 风控参数 override 重放 |
| GET | `/memory/episodes` | 列出最近 reflection 记忆 |
| POST | `/run` | 触发一次完整图运行 |
| WS | `/ws/events` | 实时事件推送 |

### 5.2 EventBus

- Pub/Sub 模式，WebSocket 客户端订阅后实时收到 graph 运行事件
- 事件类型：`node_start`, `node_end`, `decision`, `error`
- 启动：`uv run uvicorn newsalpha.api.app:app --reload`

---

## 6. Streamlit Dashboard

5 个交互页面：

| 页面 | 功能 |
|---|---|
| **Decisions** | 所有快照列表 + conviction/bias/accept 指标 + JSON 展开 |
| **Debate Viewer** | Bull vs Bear arguments 对照 + Judge verdict |
| **Backtest** | 从 `data/reports/` 加载指标 + Markdown 报告 |
| **Memory** | 最近 30 条 reflection episodes |
| **Replay (A/B)** | 选快照 → 改风控参数 → 对比原始 vs 重放结果 |

启动：`uv run streamlit run src/newsalpha/dashboard/app.py`

---

## 7. 累计成果

| 项目 | W4 末 | W5 末 | 增量 |
|---|---|---|---|
| Python 模块 | 43 | 52 | +9 |
| 测试文件 | 14 | 17 | +3 |
| 测试数量 | 81 | 108 | +27 |
| 代码行 | ~3,800 | ~5,000 | +1,200 |
| W5 核心覆盖率 | — | broker 63% / sizing 100% / macro 98% / portfolio 100% | — |

### 7.1 12 智能体状态

| # | Agent | 状态 |
|---|---|---|
| 1 | NewsCollector | ✅ W1 |
| 2-4 | Sentiment / Fundamental / Technical | ✅ W2 |
| 5-7 | Bull / Bear / DebateJudge | ✅ W3 |
| 8 | Trader (Opus 4.7) | ✅ W3 |
| 9 | RiskManager | ✅ W3 |
| 10 | ReflectionAgent | ✅ W4 |
| 11 | **MacroAnalyst** | ✅ **W5** |
| 12 | **PortfolioManager** | ✅ **W5** |

**🎉 12 智能体全部完成。**

### 7.2 三大差异化亮点

| 亮点 | 状态 |
|---|---|
| ① A/B 辩论机制 | ✅ W3 完成 |
| ② 决策快照回放 | ✅ W4 完成 + **W5 Dashboard 可视化 Replay A/B 对比** |
| ③ Reflection 记忆 | ✅ W4 写入 + **W5 Dashboard Memory 页面** |

### 7.3 完整技术栈

| 层 | 技术 |
|---|---|
| LLM | Anthropic Claude (Opus 4.7 / Sonnet 4.6 / Haiku 4.5) |
| 编排 | LangGraph (StateGraph + parallel fan-out) |
| 数据 | yfinance + Finnhub + NewsAPI + MockConnectors |
| 回测 | backtrader + quantstats |
| 向量存储 | Qdrant (prod) / InMemoryEpisodeStore (dev) |
| 执行 | Alpaca (paper/live) + MockBroker |
| API | FastAPI + WebSocket |
| 可视化 | Streamlit |
| 配置 | pydantic-settings + YAML |
| 测试 | pytest + monkeypatch (108 tests) |

---

## 8. 已知限制 & W6 路线

### 8.1 W5 留下的债

- AlpacaBroker 实际 API 调用未在 CI 中测试（需 paper 账号凭证）→ broker 覆盖率 63%
- `embed_text()` 仍为哈希占位 — 语义检索 quality 需切真 embedding 模型
- FastAPI 未加鉴权 — 研究/本地使用无碍，生产部署前需补 JWT/API-key
- Dashboard 未接 live WebSocket 更新 — 当前为刷新式

### 8.2 W6 路线

1. **长回测 2020-2025**：选 4 个 regime 段（COVID crisis / 2021 bull / 2022 bear / 2023-24 recovery），生成合成信号 → 全量 backtrader 跑通 → 性能指标对比
2. **决策图谱可视化**：Plotly Sankey / Streamlit Graph 组件，展示信号流经各节点的决策路径
3. **文档 / 架构图 / CLI 打磨**：README 重写、architecture.md、make targets、v1.0 tag
4. **最终测试 + W6 报告**

---

## 9. 进度判断

按 6 周计划，W5 末交付：
- ✅ 12 智能体全部完成（MacroAnalyst + PortfolioManager 补全）
- ✅ 执行层完整（Broker + Sizing + 安全开关）
- ✅ FastAPI + WebSocket 实时推送
- ✅ Streamlit Dashboard 5 页交互
- ✅ Graph 拓扑更新 + 端到端测试
- ✅ 108 个测试全绿

**结论：W5 完整完成；12 智能体拓扑闭合，可进入 W6 收官阶段。**
