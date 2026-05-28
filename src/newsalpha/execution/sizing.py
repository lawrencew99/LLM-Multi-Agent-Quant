"""Position sizing utilities — Kelly fraction, vol target.

These transforms run AFTER RiskManager accepts a signal but BEFORE order
submission. Pure-Python deterministic — never delegated to LLM.
"""

from __future__ import annotations


def fractional_kelly(p_win: float, win_loss_ratio: float, fraction: float = 0.25) -> float:
    """Fractional Kelly criterion for position sizing.

    f* = (p × b - (1-p)) / b  where b = win/loss ratio
    Returns fraction of capital to risk; clamped to [0, fraction] for safety.

    fraction=0.25 (quarter-Kelly) is standard for "Kelly with realistic edge
    uncertainty" — full Kelly assumes perfect knowledge and overbets.
    """
    if p_win <= 0 or p_win >= 1 or win_loss_ratio <= 0:
        return 0.0
    full_kelly = (p_win * win_loss_ratio - (1 - p_win)) / win_loss_ratio
    if full_kelly <= 0:
        return 0.0
    return min(fraction, full_kelly * fraction)


def vol_target_size(
    base_size_pct: float,
    asset_vol: float,
    target_vol: float = 0.15,
) -> float:
    """Scale base size by vol-targeting: target_vol / realized_vol.

    Caps at 1.5× upsize and 0.25× downsize to prevent extreme leverage shifts.
    """
    if asset_vol <= 0:
        return base_size_pct
    ratio = target_vol / asset_vol
    ratio = max(0.25, min(1.5, ratio))
    return base_size_pct * ratio


def conviction_scaled_size(
    base_size_pct: float,
    conviction: float,
    *,
    floor: float = 0.5,
    ceiling: float = 1.0,
) -> float:
    """Scale size by conviction. conviction=0.6 → floor; 1.0 → ceiling."""
    if conviction < 0.6:
        return 0.0
    normalized = (conviction - 0.6) / 0.4  # 0..1
    multiplier = floor + (ceiling - floor) * normalized
    return base_size_pct * multiplier


def compute_final_size(
    base_size_pct: float,
    *,
    conviction: float,
    asset_vol: float | None = None,
    p_win: float | None = None,
    win_loss_ratio: float | None = None,
    target_vol: float = 0.15,
    max_single_pct: float = 0.05,
) -> dict[str, float]:
    """Apply the full sizing pipeline; return breakdown for audit.

    final = base × conviction_mult × kelly_cap × vol_adj
    """
    conv_size = conviction_scaled_size(base_size_pct, conviction)

    kelly_factor = 1.0
    if p_win is not None and win_loss_ratio is not None:
        kelly = fractional_kelly(p_win, win_loss_ratio)
        if kelly > 0:
            kelly_factor = min(1.0, kelly / 0.05)
    after_kelly = conv_size * kelly_factor

    vol_factor = 1.0
    if asset_vol is not None and asset_vol > 0:
        vol_factor = max(0.25, min(1.5, target_vol / asset_vol))
    final_size = after_kelly * vol_factor

    final_size = min(final_size, max_single_pct)

    return {
        "base_size_pct": base_size_pct,
        "after_conviction": conv_size,
        "kelly_factor": kelly_factor,
        "after_kelly": after_kelly,
        "vol_factor": vol_factor,
        "final_size_pct": final_size,
    }
