from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any

import anthropic
from anthropic.types import Message
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from newsalpha.core.config import get_settings
from newsalpha.llm.budget import get_budget_tracker
from newsalpha.llm.routing import AgentLLMConfig, estimate_cost, supports_temperature
from newsalpha.utils.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class LLMCallResult:
    """Outcome of one Anthropic call — text, parsed JSON if applicable, usage."""

    text: str
    parsed: dict[str, Any] | None
    raw_message: Message
    cost_usd: float
    latency_ms: int
    cache_read_tokens: int
    cache_write_tokens: int


class AnthropicClient:
    """Thin wrapper around `anthropic.Anthropic` with caching, retries, and cost tracking.

    Single instance per process — share it across agents.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key.get_secret_value())
        self._budget = get_budget_tracker()

    @retry(
        retry=retry_if_exception_type(
            (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.APIStatusError)
        ),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def call(
        self,
        agent_cfg: AgentLLMConfig,
        *,
        system: str | list[dict[str, Any]],
        messages: list[dict[str, Any]],
        expect_json: bool = False,
    ) -> LLMCallResult:
        """Issue one Messages API call. Cache the (tools+) system prefix automatically.

        - `system` may be a plain string (auto-wrapped with a cache_control breakpoint
          when `agent_cfg.cache_system_prompt` is true) or a pre-built block list.
        - `expect_json=True` attempts `json.loads()` on the model's text output and
          fills `LLMCallResult.parsed`; on parse failure, `parsed` is None and the
          raw text remains available.
        """
        system_payload = self._build_system(system, cache=agent_cfg.cache_system_prompt)

        kwargs: dict[str, Any] = {
            "model": agent_cfg.model_id,
            "max_tokens": agent_cfg.max_tokens,
            "system": system_payload,
            "messages": messages,
        }
        if supports_temperature(agent_cfg.model_id):
            kwargs["temperature"] = agent_cfg.temperature
        if agent_cfg.effort is not None:
            kwargs["output_config"] = {"effort": agent_cfg.effort}

        t0 = time.perf_counter()
        msg = self._client.messages.create(**kwargs)
        latency_ms = int((time.perf_counter() - t0) * 1000)

        usage = msg.usage
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
        cost = estimate_cost(
            agent_cfg.model_id,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_write_tokens=cache_write,
            cache_read_tokens=cache_read,
        )

        self._budget.add(cost)

        text = "".join(b.text for b in msg.content if b.type == "text")
        parsed: dict[str, Any] | None = None
        if expect_json:
            parsed = _try_parse_json(text)
            if parsed is None:
                log.warning(
                    "llm_json_parse_failed",
                    agent=agent_cfg.agent,
                    model=agent_cfg.model_alias,
                    preview=text[:200],
                )

        log.info(
            "llm_call_completed",
            agent=agent_cfg.agent,
            model=agent_cfg.model_alias,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read=cache_read,
            cache_write=cache_write,
            cost_usd=round(cost, 5),
            latency_ms=latency_ms,
        )

        return LLMCallResult(
            text=text,
            parsed=parsed,
            raw_message=msg,
            cost_usd=cost,
            latency_ms=latency_ms,
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_write,
        )

    async def acall(self, *args: Any, **kwargs: Any) -> LLMCallResult:
        """Async wrapper for `call`. Runs the sync client in a thread for now;
        upgrade to AsyncAnthropic once we hit concurrency limits."""
        return await asyncio.to_thread(self.call, *args, **kwargs)

    @staticmethod
    def _build_system(
        system: str | list[dict[str, Any]],
        *,
        cache: bool,
    ) -> list[dict[str, Any]]:
        if isinstance(system, list):
            return system
        block: dict[str, Any] = {"type": "text", "text": system}
        if cache:
            block["cache_control"] = {"type": "ephemeral"}
        return [block]


def _try_parse_json(text: str) -> dict[str, Any] | None:
    """Permissive JSON extraction: handles fenced ```json blocks and stripped prose."""
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.lower().startswith("json"):
            candidate = candidate[4:]
        candidate = candidate.strip()
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        obj = json.loads(candidate[start : end + 1])
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


_client: AnthropicClient | None = None


def get_llm_client() -> AnthropicClient:
    global _client
    if _client is None:
        _client = AnthropicClient()
    return _client
