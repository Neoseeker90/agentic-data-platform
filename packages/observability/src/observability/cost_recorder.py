"""CostRecorder — estimates and persists LLM token cost records."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from contracts.cost import TokenCostRecord


class CostRecorder:
    """Records LLM token usage and estimated costs.

    If a ``store`` is provided it is called to persist each record; otherwise
    records are returned but not saved anywhere.
    """

    # Cost per 1K tokens (USD) — conservative estimates.
    # Includes both Anthropic API IDs and Bedrock cross-region inference profile IDs.
    COST_PER_1K_INPUT: dict[str, Decimal] = {
        # Anthropic API
        "claude-3-haiku-20240307": Decimal("0.00025"),
        "claude-3-5-haiku-20241022": Decimal("0.00080"),
        "claude-3-5-sonnet-20241022": Decimal("0.003"),
        "claude-sonnet-4-6": Decimal("0.003"),
        "claude-opus-4-6": Decimal("0.015"),
        # Bedrock cross-region (us / eu / ap prefixes — same pricing as direct API)
        "us.anthropic.claude-3-haiku-20240307-v1:0": Decimal("0.00025"),
        "eu.anthropic.claude-3-haiku-20240307-v1:0": Decimal("0.00025"),
        "us.anthropic.claude-3-5-haiku-20241022-v1:0": Decimal("0.00080"),
        "eu.anthropic.claude-3-5-haiku-20241022-v1:0": Decimal("0.00080"),
        "us.anthropic.claude-3-5-sonnet-20241022-v2:0": Decimal("0.003"),
        "eu.anthropic.claude-3-5-sonnet-20241022-v2:0": Decimal("0.003"),
        "us.anthropic.claude-sonnet-4-5-20251101-v1:0": Decimal("0.003"),
        "eu.anthropic.claude-sonnet-4-5-20251101-v1:0": Decimal("0.003"),
        # OpenAI
        "gpt-4o": Decimal("0.0025"),
        "gpt-4o-mini": Decimal("0.00015"),
        "gpt-4-turbo": Decimal("0.010"),
        "gpt-4": Decimal("0.030"),
        "o1": Decimal("0.015"),
        "o1-mini": Decimal("0.003"),
    }
    COST_PER_1K_OUTPUT: dict[str, Decimal] = {
        # Anthropic API
        "claude-3-haiku-20240307": Decimal("0.00125"),
        "claude-3-5-haiku-20241022": Decimal("0.004"),
        "claude-3-5-sonnet-20241022": Decimal("0.015"),
        "claude-sonnet-4-6": Decimal("0.015"),
        "claude-opus-4-6": Decimal("0.075"),
        # Bedrock cross-region
        "us.anthropic.claude-3-haiku-20240307-v1:0": Decimal("0.00125"),
        "eu.anthropic.claude-3-haiku-20240307-v1:0": Decimal("0.00125"),
        "us.anthropic.claude-3-5-haiku-20241022-v1:0": Decimal("0.004"),
        "eu.anthropic.claude-3-5-haiku-20241022-v1:0": Decimal("0.004"),
        "us.anthropic.claude-3-5-sonnet-20241022-v2:0": Decimal("0.015"),
        "eu.anthropic.claude-3-5-sonnet-20241022-v2:0": Decimal("0.015"),
        "us.anthropic.claude-sonnet-4-5-20251101-v1:0": Decimal("0.015"),
        "eu.anthropic.claude-sonnet-4-5-20251101-v1:0": Decimal("0.015"),
        # OpenAI
        "gpt-4o": Decimal("0.010"),
        "gpt-4o-mini": Decimal("0.00060"),
        "gpt-4-turbo": Decimal("0.030"),
        "gpt-4": Decimal("0.060"),
        "o1": Decimal("0.060"),
        "o1-mini": Decimal("0.012"),
    }

    _FALLBACK_MODEL = "claude-sonnet-4-6"

    def __init__(self, store: object = None) -> None:
        # store is optional — if None, records are returned but not persisted
        self._store = store

    def estimate_cost(
        self,
        model_id: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> Decimal:
        """Return USD cost estimate for the given token counts.

        Falls back to claude-sonnet-4-6 rates for unknown model IDs.
        """
        input_rate = self.COST_PER_1K_INPUT.get(
            model_id, self.COST_PER_1K_INPUT[self._FALLBACK_MODEL]
        )
        output_rate = self.COST_PER_1K_OUTPUT.get(
            model_id, self.COST_PER_1K_OUTPUT[self._FALLBACK_MODEL]
        )
        return (
            Decimal(prompt_tokens) * input_rate / Decimal(1000)
            + Decimal(completion_tokens) * output_rate / Decimal(1000)
        )

    async def record(
        self,
        run_id: UUID,
        stage: str,
        skill_name: str | None,
        provider: str,
        model_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: int,
        error: str | None = None,
    ) -> TokenCostRecord:
        """Build a :class:`TokenCostRecord`, optionally persist it, and return it."""
        cost = self.estimate_cost(model_id, prompt_tokens, completion_tokens)
        record = TokenCostRecord(
            run_id=run_id,
            skill_name=skill_name,
            stage=stage,
            provider=provider,
            model_id=model_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            estimated_cost_usd=cost,
            latency_ms=latency_ms,
            error=error,
            recorded_at=datetime.now(UTC),
        )
        if self._store is not None:
            await self._store.save(record)
        return record

    @staticmethod
    def timer() -> "CostTimer":
        """Return a new :class:`CostTimer` context manager."""
        return CostTimer()


class CostTimer:
    """Context manager for measuring LLM call latency in milliseconds."""

    def __init__(self) -> None:
        self._start: float | None = None
        self._end: float | None = None

    def __enter__(self) -> "CostTimer":
        self._start = time.monotonic()
        return self

    def __exit__(self, *args: object) -> None:
        self._end = time.monotonic()

    @property
    def elapsed_ms(self) -> int:
        """Return elapsed time in milliseconds.

        Raises ``RuntimeError`` if the timer has not been started and stopped.
        """
        if self._start is None or self._end is None:
            raise RuntimeError("CostTimer must be used as a context manager before reading elapsed_ms")
        return int((self._end - self._start) * 1000)
