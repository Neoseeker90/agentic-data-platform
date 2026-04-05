from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from contracts.feedback import FeedbackFailureReason, FeedbackRecord, ImplicitSignal
from feedback.service import FeedbackService


def _make_run_id() -> uuid.UUID:
    return uuid.uuid4()


def _make_record(run_id: uuid.UUID, user_id: str, **kwargs) -> FeedbackRecord:
    return FeedbackRecord(
        run_id=run_id,
        user_id=user_id,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_capture_explicit_creates_record() -> None:
    run_id = _make_run_id()
    user_id = "user-abc"

    expected_record = _make_record(run_id, user_id, score=4, helpful=True)
    store = AsyncMock()
    store.create = AsyncMock(return_value=expected_record)

    service = FeedbackService(store=store)
    result = await service.capture_explicit(
        run_id=run_id,
        user_id=user_id,
        score=4,
        helpful=True,
    )

    store.create.assert_called_once()
    call_arg: FeedbackRecord = store.create.call_args[0][0]
    assert call_arg.run_id == run_id
    assert call_arg.user_id == user_id
    assert call_arg.score == 4
    assert call_arg.helpful is True
    assert result is expected_record


@pytest.mark.asyncio
async def test_capture_explicit_validates_score() -> None:
    run_id = _make_run_id()
    store = AsyncMock()
    service = FeedbackService(store=store)

    with pytest.raises(Exception):  # noqa: B017
        await service.capture_explicit(
            run_id=run_id,
            user_id="user-xyz",
            score=6,
        )

    store.create.assert_not_called()


@pytest.mark.asyncio
async def test_capture_implicit_calls_append() -> None:
    run_id = _make_run_id()
    user_id = "user-def"
    signal = ImplicitSignal.CLICKED_DASHBOARD

    expected_record = _make_record(run_id, user_id, implicit_signals=[signal])
    store = AsyncMock()
    store.append_implicit_signal = AsyncMock(return_value=expected_record)

    service = FeedbackService(store=store)
    result = await service.capture_implicit(
        run_id=run_id,
        user_id=user_id,
        signal=signal,
    )

    store.append_implicit_signal.assert_called_once_with(run_id, user_id, signal)
    assert result is expected_record


@pytest.mark.asyncio
async def test_capture_explicit_with_failure_reason() -> None:
    run_id = _make_run_id()
    user_id = "user-ghi"
    reason = FeedbackFailureReason.WRONG_SKILL_SELECTED

    expected_record = _make_record(run_id, user_id, failure_reason=reason)
    store = AsyncMock()
    store.create = AsyncMock(return_value=expected_record)

    service = FeedbackService(store=store)
    result = await service.capture_explicit(
        run_id=run_id,
        user_id=user_id,
        failure_reason=reason,
    )

    store.create.assert_called_once()
    call_arg: FeedbackRecord = store.create.call_args[0][0]
    assert call_arg.failure_reason == reason
    assert result is expected_record
