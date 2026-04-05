from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from agent_api.db.models import FeedbackORM
from contracts.feedback import FeedbackRecord, ImplicitSignal
from feedback.db.feedback_store import FeedbackStore


# ---------------------------------------------------------------------------
# Session / factory helpers
# ---------------------------------------------------------------------------


class _MockScalars:
    def __init__(self, items: list[Any]) -> None:
        self._items = items

    def first(self) -> Any | None:
        return self._items[0] if self._items else None

    def all(self) -> list[Any]:
        return self._items


class _MockResult:
    def __init__(self, items: list[Any]) -> None:
        self._items = items

    def scalars(self) -> _MockScalars:
        return _MockScalars(self._items)

    def scalar_one(self) -> Any:
        return self._items[0] if self._items else None


class _MockSession:
    def __init__(self, execute_returns: list[list[Any]] | None = None) -> None:
        self._execute_returns = execute_returns or [[]]
        self._call_count = 0
        self.added: list[Any] = []
        self.committed = False

    async def execute(self, *_args: Any, **_kwargs: Any) -> _MockResult:
        items = self._execute_returns[self._call_count]
        self._call_count += 1
        return _MockResult(items)

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, obj: Any) -> None:
        # Simulate DB filling in captured_at so _to_record doesn't get None.
        if isinstance(obj, FeedbackORM) and obj.captured_at is None:
            obj.captured_at = datetime.now(UTC)

    async def __aenter__(self) -> _MockSession:
        return self

    async def __aexit__(self, *_: Any) -> None:
        pass


def _make_factory(sessions: list[_MockSession]):
    idx: list[int] = [0]

    def factory() -> _MockSession:
        s = sessions[idx[0]]
        idx[0] += 1
        return s

    return factory


def _make_record(run_id: uuid.UUID | None = None) -> FeedbackRecord:
    return FeedbackRecord(
        feedback_id=uuid.uuid4(),
        run_id=run_id or uuid.uuid4(),
        user_id="test-user",
        helpful=True,
        score=4,
        comment="great",
        failure_reason=None,
        implicit_signals=[],
        captured_at=datetime.now(UTC),
    )


def _make_orm(record: FeedbackRecord) -> FeedbackORM:
    return FeedbackORM(
        feedback_id=record.feedback_id,
        run_id=record.run_id,
        user_id=record.user_id,
        helpful=record.helpful,
        score=record.score,
        comment=record.comment,
        failure_reason=None,
        implicit_signals=[],
        captured_at=record.captured_at,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_persists_feedback_orm() -> None:
    record = _make_record()
    orm_to_return = _make_orm(record)

    session = _MockSession(execute_returns=[[]])
    # After add+commit+refresh, scalars will return our orm
    # But create() doesn't call execute — it just calls add/commit/refresh.
    # We need refresh to populate the orm so _to_record works.
    # Patch refresh to set fields from record.
    async def _refresh(obj: Any) -> None:
        # Already set from constructor; nothing to do.
        pass

    session.refresh = _refresh  # type: ignore[method-assign]

    factory = _make_factory([session])
    store = FeedbackStore(session_factory=factory)

    # Patch _from_record to return our orm_to_return so we can track `add`
    with patch.object(FeedbackStore, "_from_record", return_value=orm_to_return):
        result = await store.create(record)

    assert session.added == [orm_to_return]
    assert session.committed is True


@pytest.mark.asyncio
async def test_append_implicit_signal_creates_new_when_none_exists() -> None:
    run_id = uuid.uuid4()
    user_id = "user-123"
    signal = ImplicitSignal.CLICKED_DASHBOARD

    # First execute (SELECT) returns nothing → no existing record
    session = _MockSession(execute_returns=[[]])
    factory = _make_factory([session])
    store = FeedbackStore(session_factory=factory)

    result = await store.append_implicit_signal(run_id, user_id, signal)

    # A new ORM row should have been added
    assert len(session.added) == 1
    added_orm: FeedbackORM = session.added[0]
    assert added_orm.run_id == run_id
    assert added_orm.user_id == user_id
    assert signal.value in added_orm.implicit_signals
    assert session.committed is True

    assert result.run_id == run_id
    assert result.user_id == user_id
    assert ImplicitSignal(signal.value) in result.implicit_signals


@pytest.mark.asyncio
async def test_list_low_rated_filters_by_threshold() -> None:
    run_id = uuid.uuid4()
    low_orm = FeedbackORM(
        feedback_id=uuid.uuid4(),
        run_id=run_id,
        user_id="u1",
        helpful=False,
        score=1,
        comment=None,
        failure_reason=None,
        implicit_signals=[],
        captured_at=datetime.now(UTC),
    )

    session = _MockSession(execute_returns=[[low_orm]])
    factory = _make_factory([session])
    store = FeedbackStore(session_factory=factory)

    results = await store.list_low_rated(score_threshold=2, limit=10)

    assert len(results) == 1
    assert results[0].run_id == run_id
    assert results[0].score == 1
