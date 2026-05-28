from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from newsalpha.agents.bear_researcher import bear_researcher
from newsalpha.agents.bull_researcher import bull_researcher
from newsalpha.agents.debate_judge import debate_judge
from newsalpha.agents.debate_orchestrator import (
    debate_orchestrator,
    debate_round_advancer,
    log_only,
    should_continue_debate,
    should_trade,
)
from newsalpha.agents.fundamental_analyst import fundamental_analyst
from newsalpha.agents.macro_analyst import macro_analyst
from newsalpha.agents.news_collector import news_collector
from newsalpha.agents.portfolio_manager import portfolio_manager
from newsalpha.agents.risk_manager import risk_manager
from newsalpha.agents.sentiment_analyst import sentiment_analyst
from newsalpha.agents.technical_analyst import technical_analyst
from newsalpha.agents.trader import trader
from newsalpha.core.state import TradingState


def _analysts_join(state: TradingState) -> dict[str, Any]:
    """Sync barrier after the three parallel analysts (no state mutation)."""
    return {}


def build_graph() -> Any:
    """W5 graph: news → 4 parallel analysts (incl. macro) → debate → judge
                    → trader → risk → portfolio → END.

    Topology:

        START → news_collector
                ↓ (fan-out)
        sentiment / fundamental / technical / macro
                ↓ (fan-in)
        analysts_ready → debate_orchestrator → bull_researcher → bear_researcher
                                                                  ↓
                                            (round < N) ← round_advancer
                                                                  ↓ (round == N)
                                                              debate_judge
                                                                  ↓
                                              conviction < 0.6 → log_only → END
                                              conviction ≥ 0.6 → trader
                                                                  ↓
                                                              risk_manager
                                                                  ↓
                                                          portfolio_manager → END

    Bull and Bear are sequential within a round on purpose: in `adversarial`
    mode the bear must engage with the bull's just-stated claims. `panel` mode
    works under the same topology — its prompt simply ignores prior bull args.
    """
    g: StateGraph = StateGraph(TradingState)

    g.add_node("news_collector", news_collector)
    g.add_node("sentiment_analyst", sentiment_analyst)
    g.add_node("fundamental_analyst", fundamental_analyst)
    g.add_node("technical_analyst", technical_analyst)
    g.add_node("macro_analyst", macro_analyst)
    g.add_node("analysts_ready", _analysts_join)
    g.add_node("debate_orchestrator", debate_orchestrator)
    g.add_node("bull_researcher", bull_researcher)
    g.add_node("bear_researcher", bear_researcher)
    g.add_node("round_advancer", debate_round_advancer)
    g.add_node("debate_judge", debate_judge)
    g.add_node("trader", trader)
    g.add_node("risk_manager", risk_manager)
    g.add_node("portfolio_manager", portfolio_manager)
    g.add_node("log_only", log_only)

    g.add_edge(START, "news_collector")
    g.add_edge("news_collector", "sentiment_analyst")
    g.add_edge("news_collector", "fundamental_analyst")
    g.add_edge("news_collector", "technical_analyst")
    g.add_edge("news_collector", "macro_analyst")
    g.add_edge("sentiment_analyst", "analysts_ready")
    g.add_edge("fundamental_analyst", "analysts_ready")
    g.add_edge("technical_analyst", "analysts_ready")
    g.add_edge("macro_analyst", "analysts_ready")

    g.add_edge("analysts_ready", "debate_orchestrator")
    g.add_edge("debate_orchestrator", "bull_researcher")
    g.add_edge("bull_researcher", "bear_researcher")
    g.add_edge("bear_researcher", "round_advancer")

    g.add_conditional_edges(
        "round_advancer",
        should_continue_debate,
        {
            "continue": "bull_researcher",
            "judge": "debate_judge",
        },
    )

    g.add_conditional_edges(
        "debate_judge",
        should_trade,
        {
            "trade": "trader",
            "stop": "log_only",
        },
    )

    g.add_edge("trader", "risk_manager")
    g.add_edge("risk_manager", "portfolio_manager")
    g.add_edge("portfolio_manager", END)
    g.add_edge("log_only", END)

    return g.compile()
