"""ReflectionAgent — post-trade analysis and memory write.

Triggered asynchronously after a position is closed. Examines the full
decision snapshot + actual PnL, generates structured lessons, then writes
an Episode to the vector store so future debates can retrieve similar cases.
"""

from __future__ import annotations

import json
from typing import Any

from newsalpha.agents.base import call_agent
from newsalpha.memory.episodes import Episode, embed_text, get_default_store, write_episode
from newsalpha.utils.logging import get_logger

log = get_logger(__name__)

AGENT_NAME = "reflection"


def reflect_on_trade(
    trade_result: dict[str, Any],
    *,
    decision_state: dict[str, Any] | None = None,
    regime: str = "unknown",
) -> Episode:
    """Run the ReflectionAgent on a closed trade, produce and store an Episode.

    Args:
        trade_result: From backtest engine trade_log entry (ticker, side,
                      entry_date, exit_date, pnl_pct, conviction, trace_id).
        decision_state: Original TradingState snapshot — the analyst reports,
                        debate arguments, etc.
        regime: Current macro regime label (bull/bear/chop/crisis).
    """
    ticker = trade_result.get("ticker", "")
    side = trade_result.get("side", "")
    pnl_pct = float(trade_result.get("pnl_pct", 0.0))
    conviction = float(trade_result.get("conviction", 0.0))

    payload = json.dumps(
        {
            "ticker": ticker,
            "side": side,
            "entry_date": trade_result.get("entry_date", ""),
            "exit_date": trade_result.get("exit_date", ""),
            "pnl_pct": pnl_pct,
            "conviction": conviction,
            "exit_reason": trade_result.get("exit_reason", ""),
            "regime": regime,
            "analyst_reports": {
                "sentiment": (decision_state or {}).get("sentiment_report"),
                "fundamental": (decision_state or {}).get("fundamental_report"),
                "technical": (decision_state or {}).get("technical_report"),
            },
            "judge_verdict": (decision_state or {}).get("judge_verdict"),
            "bull_arguments": (decision_state or {}).get("bull_arguments", []),
            "bear_arguments": (decision_state or {}).get("bear_arguments", []),
        },
        default=str,
    )

    try:
        result = call_agent(AGENT_NAME, user_payload=payload)
        parsed = result.parsed or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("reflection_agent_failed", ticker=ticker, error=str(exc))
        parsed = {
            "what_worked": [],
            "what_failed": [],
            "lessons": [f"Reflection failed: {exc}"],
            "key_signals": [],
        }

    episode = Episode(
        ticker=ticker,
        side=side,
        entry_date=trade_result.get("entry_date", ""),
        exit_date=trade_result.get("exit_date", ""),
        pnl_pct=pnl_pct,
        conviction=conviction,
        regime=regime,
        what_worked=parsed.get("what_worked", []),
        what_failed=parsed.get("what_failed", []),
        lessons=parsed.get("lessons", []),
        key_signals=parsed.get("key_signals", []),
        trace_id=trade_result.get("trace_id", ""),
    )

    write_episode(episode)
    return episode


def reflect_batch(
    trade_log: list[dict[str, Any]],
    *,
    regime: str = "unknown",
) -> list[Episode]:
    """Reflect on multiple trades (e.g., after a backtest run).

    Uses a mock reflection (no LLM) to produce Episodes from PnL analysis.
    """
    episodes: list[Episode] = []

    for trade in trade_log:
        pnl = float(trade.get("pnl_pct", 0.0))
        ticker = trade.get("ticker", "")
        exit_reason = trade.get("exit_reason", "")

        if pnl > 0:
            what_worked = [f"Trade was profitable ({pnl*100:.1f}%)"]
            what_failed = []
            lessons = [f"High conviction trade on {ticker} paid off"]
        else:
            what_worked = []
            what_failed = [f"Trade lost money ({pnl*100:.1f}%)"]
            lessons = [f"Review {exit_reason} conditions for {ticker}"]

        episode = Episode(
            ticker=ticker,
            side=trade.get("side", ""),
            entry_date=trade.get("entry_date", ""),
            exit_date=trade.get("exit_date", ""),
            pnl_pct=pnl,
            conviction=float(trade.get("conviction", 0.0)),
            regime=regime,
            what_worked=what_worked,
            what_failed=what_failed,
            lessons=lessons,
            key_signals=[],
            trace_id=trade.get("trace_id", ""),
        )
        write_episode(episode)
        episodes.append(episode)

    log.info("reflection_batch_complete", n_trades=len(trade_log), n_episodes=len(episodes))
    return episodes
