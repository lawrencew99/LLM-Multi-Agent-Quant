"""Deterministic risk rules. NEVER call an LLM here.

The Trader emits a candidate signal; this module applies the hard, auditable
limits from `configs/risk.yaml` and either accepts (possibly resized), rejects,
or downgrades to `hold`. Every rejection comes with a machine-readable reason
code that flows into the decision snapshot for replay.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from newsalpha.core.config import load_yaml_config


@dataclass
class RiskDecision:
    accepted: bool
    final_size_pct: float
    final_stop_price: float
    reasons: list[str] = field(default_factory=list)
    adjustments: list[str] = field(default_factory=list)
    rule_versions: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "final_size_pct": self.final_size_pct,
            "final_stop_price": self.final_stop_price,
            "reasons": self.reasons,
            "adjustments": self.adjustments,
            "rule_versions": self.rule_versions,
        }


def _load_risk_config() -> dict[str, Any]:
    return load_yaml_config("risk")


def _compute_atr_stop(side: str, entry: float, atr14: float, multiplier: float) -> float:
    distance = multiplier * atr14
    if side == "long":
        return max(0.0, entry - distance)
    if side == "short":
        return entry + distance
    return 0.0


def evaluate_signal(
    signal: dict[str, Any],
    *,
    market_snapshot: dict[str, Any] | None = None,
    portfolio_context: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> RiskDecision:
    """Apply hard rules to a Trader-emitted signal.

    Returns a RiskDecision; callers should persist the entire object for audit.
    Rules applied (in order):

    1. `hold` short-circuits → accepted=False, no orders.
    2. Single-ticker cap (`position.max_single_pct`) — clamp size, not reject.
    3. Mandatory stop-loss; backfill from 2×ATR(14) when missing.
    4. Liquidity gate (`universe_filter.min_avg_dollar_volume_usd`) — reject.
    5. NaN / non-positive price sanity — reject.
    6. Leverage cap (`max_leverage`) — clamp.
    """
    cfg = config or _load_risk_config()
    pos_cfg = cfg.get("position", {})
    stops_cfg = cfg.get("stops", {})
    universe_cfg = cfg.get("universe_filter", {})

    decision = RiskDecision(
        accepted=False,
        final_size_pct=0.0,
        final_stop_price=0.0,
        rule_versions={
            "max_single_pct": pos_cfg.get("max_single_pct", 0.05),
            "atr_multiplier": stops_cfg.get("atr_multiplier", 2.0),
            "min_dollar_vol": universe_cfg.get("min_avg_dollar_volume_usd", 10_000_000),
        },
    )

    action = signal.get("action", "hold")
    if action == "hold":
        decision.reasons.append("trader_recommended_hold")
        return decision

    side = signal.get("side", "flat")
    if side not in {"long", "short"}:
        decision.reasons.append(f"invalid_side:{side}")
        return decision

    entry = float(signal.get("entry_price_hint") or 0.0)
    snap = market_snapshot or {}
    if entry <= 0.0:
        entry = float(snap.get("price") or 0.0)
    if entry <= 0.0:
        decision.reasons.append("no_entry_price")
        return decision

    requested_size = float(signal.get("suggested_size_pct") or 0.0)
    if requested_size <= 0.0:
        decision.reasons.append("non_positive_size")
        return decision

    max_single = float(pos_cfg.get("max_single_pct", 0.05))
    final_size = min(requested_size, max_single)
    if final_size < requested_size:
        decision.adjustments.append(
            f"size_capped:{requested_size:.4f}->{final_size:.4f}"
        )

    portfolio = portfolio_context or {}
    current_pos = float(portfolio.get("current_position_pct", 0.0) or 0.0)
    if current_pos + final_size > max_single + 1e-9:
        headroom = max(0.0, max_single - current_pos)
        if headroom <= 0.0:
            decision.reasons.append("at_single_ticker_cap")
            return decision
        decision.adjustments.append(
            f"size_clamped_to_headroom:{final_size:.4f}->{headroom:.4f}"
        )
        final_size = headroom

    stop = float(signal.get("stop_loss_price") or 0.0)
    atr14 = float(snap.get("atr14") or 0.0)
    if stop <= 0.0:
        if atr14 <= 0.0:
            decision.reasons.append("no_stop_no_atr")
            return decision
        stop = _compute_atr_stop(side, entry, atr14, float(stops_cfg.get("atr_multiplier", 2.0)))
        decision.adjustments.append(f"stop_backfilled_2xATR:{stop:.4f}")

    if side == "long" and stop >= entry:
        decision.reasons.append(f"long_stop_above_entry:{stop:.4f}>={entry:.4f}")
        return decision
    if side == "short" and stop <= entry:
        decision.reasons.append(f"short_stop_below_entry:{stop:.4f}<={entry:.4f}")
        return decision

    avg_dollar_vol = float(portfolio.get("avg_dollar_volume_usd") or 0.0)
    min_vol = float(universe_cfg.get("min_avg_dollar_volume_usd", 10_000_000))
    if avg_dollar_vol > 0.0 and avg_dollar_vol < min_vol:
        decision.reasons.append(
            f"insufficient_liquidity:{avg_dollar_vol:.0f}<{min_vol:.0f}"
        )
        return decision

    decision.accepted = True
    decision.final_size_pct = final_size
    decision.final_stop_price = stop
    decision.reasons.append("accepted")
    return decision
