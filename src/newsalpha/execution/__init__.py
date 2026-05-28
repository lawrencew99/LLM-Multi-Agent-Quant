"""Execution layer — broker abstractions and position sizing."""

from __future__ import annotations

from newsalpha.execution.broker import (
    AccountSummary,
    AlpacaBroker,
    BaseBroker,
    MockBroker,
    OrderResult,
    Position,
    get_default_broker,
)
from newsalpha.execution.sizing import (
    compute_final_size,
    conviction_scaled_size,
    fractional_kelly,
    vol_target_size,
)

__all__ = [
    "AccountSummary",
    "AlpacaBroker",
    "BaseBroker",
    "MockBroker",
    "OrderResult",
    "Position",
    "compute_final_size",
    "conviction_scaled_size",
    "fractional_kelly",
    "get_default_broker",
    "vol_target_size",
]
