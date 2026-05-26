from __future__ import annotations

import threading
from datetime import UTC, datetime

from newsalpha.core.config import get_settings
from newsalpha.utils.logging import get_logger

log = get_logger(__name__)


class BudgetExceededError(RuntimeError):
    """Raised when the configured daily LLM budget is exhausted."""


class DailyBudgetTracker:
    """Thread-safe in-memory tracker. Resets on UTC date change.

    For W1 this lives in-process; W3+ persists to Postgres.
    """

    def __init__(self, daily_limit_usd: float) -> None:
        self._daily_limit = daily_limit_usd
        self._spent = 0.0
        self._date = self._utc_today()
        self._lock = threading.Lock()

    @staticmethod
    def _utc_today() -> str:
        return datetime.now(tz=UTC).strftime("%Y-%m-%d")

    def add(self, cost_usd: float) -> None:
        with self._lock:
            today = self._utc_today()
            if today != self._date:
                self._date = today
                self._spent = 0.0
            self._spent += cost_usd
            if self._spent > self._daily_limit:
                log.warning(
                    "llm_budget_exceeded",
                    spent=round(self._spent, 4),
                    limit=self._daily_limit,
                )
                raise BudgetExceededError(
                    f"Daily LLM budget exceeded: ${self._spent:.4f} > ${self._daily_limit}"
                )

    @property
    def spent_today(self) -> float:
        with self._lock:
            if self._utc_today() != self._date:
                return 0.0
            return self._spent


_tracker: DailyBudgetTracker | None = None


def get_budget_tracker() -> DailyBudgetTracker:
    global _tracker
    if _tracker is None:
        _tracker = DailyBudgetTracker(get_settings().llm_daily_budget_usd)
    return _tracker
