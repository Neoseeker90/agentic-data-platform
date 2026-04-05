"""Unit tests for CostRecorder and CostTimer."""

from __future__ import annotations

import time
from decimal import Decimal
from uuid import uuid4

import pytest

from observability.cost_recorder import CostRecorder, CostTimer


class TestEstimateCost:
    def test_estimate_cost_known_model(self) -> None:
        """Haiku: 1000 prompt + 200 completion tokens → correct USD."""
        recorder = CostRecorder()
        cost = recorder.estimate_cost(
            model_id="claude-3-haiku-20240307",
            prompt_tokens=1000,
            completion_tokens=200,
        )
        # 1000 * 0.00025 / 1000 + 200 * 0.00125 / 1000
        # = 0.00025 + 0.00025 = 0.00050
        expected = Decimal("0.00025") + Decimal("0.00025")
        assert cost == expected

    def test_estimate_cost_unknown_model(self) -> None:
        """Unknown model falls back to claude-sonnet-4-6 rates."""
        recorder = CostRecorder()
        cost_unknown = recorder.estimate_cost(
            model_id="totally-unknown-model-xyz",
            prompt_tokens=1000,
            completion_tokens=500,
        )
        cost_sonnet = recorder.estimate_cost(
            model_id="claude-sonnet-4-6",
            prompt_tokens=1000,
            completion_tokens=500,
        )
        assert cost_unknown == cost_sonnet

    def test_estimate_cost_zero_tokens(self) -> None:
        """Zero tokens should yield zero cost."""
        recorder = CostRecorder()
        assert recorder.estimate_cost("claude-sonnet-4-6", 0, 0) == Decimal("0")


class TestRecord:
    @pytest.mark.asyncio
    async def test_record_returns_token_cost_record(self) -> None:
        """record() with no store returns a TokenCostRecord with correct fields."""
        from contracts.cost import TokenCostRecord

        recorder = CostRecorder()
        run_id = uuid4()
        result = await recorder.record(
            run_id=run_id,
            stage="planning",
            skill_name="answer_business_question",
            provider="anthropic",
            model_id="claude-3-haiku-20240307",
            prompt_tokens=500,
            completion_tokens=100,
            latency_ms=350,
        )

        assert isinstance(result, TokenCostRecord)
        assert result.run_id == run_id
        assert result.stage == "planning"
        assert result.skill_name == "answer_business_question"
        assert result.provider == "anthropic"
        assert result.model_id == "claude-3-haiku-20240307"
        assert result.prompt_tokens == 500
        assert result.completion_tokens == 100
        assert result.total_tokens == 600
        assert result.latency_ms == 350
        assert result.error is None
        # cost: 500 * 0.00025/1000 + 100 * 0.00125/1000
        expected_cost = Decimal("0.000125") + Decimal("0.000125")
        assert result.estimated_cost_usd == expected_cost

    @pytest.mark.asyncio
    async def test_record_calls_store_save(self) -> None:
        """record() calls store.save() when a store is configured."""
        from unittest.mock import AsyncMock

        mock_store = AsyncMock()
        recorder = CostRecorder(store=mock_store)

        run_id = uuid4()
        await recorder.record(
            run_id=run_id,
            stage="execution",
            skill_name=None,
            provider="anthropic",
            model_id="claude-sonnet-4-6",
            prompt_tokens=100,
            completion_tokens=50,
            latency_ms=200,
        )

        mock_store.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_record_with_error_field(self) -> None:
        """record() propagates the error field into the returned record."""
        recorder = CostRecorder()
        result = await recorder.record(
            run_id=uuid4(),
            stage="routing",
            skill_name=None,
            provider="anthropic",
            model_id="claude-opus-4-6",
            prompt_tokens=0,
            completion_tokens=0,
            latency_ms=1000,
            error="timeout",
        )
        assert result.error == "timeout"


class TestCostTimer:
    def test_cost_timer_measures_elapsed(self) -> None:
        """CostTimer context manager returns a positive elapsed_ms."""
        with CostRecorder.timer() as t:
            time.sleep(0.01)

        assert t.elapsed_ms > 0

    def test_cost_timer_elapsed_ms_is_int(self) -> None:
        """elapsed_ms must be an integer."""
        with CostTimer() as t:
            pass

        assert isinstance(t.elapsed_ms, int)

    def test_cost_timer_raises_before_use(self) -> None:
        """Reading elapsed_ms before entering the context raises RuntimeError."""
        timer = CostTimer()
        with pytest.raises(RuntimeError):
            _ = timer.elapsed_ms
