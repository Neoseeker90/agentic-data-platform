from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest

from feedback.aggregator import FeedbackAggregator


def _make_session_factory(execute_side_effects: list[Any]):
    """Build a minimal async context-manager session factory whose execute()
    returns successive mock result objects from *execute_side_effects*."""

    call_count: list[int] = [0]

    class _MockResult:
        def __init__(self, rows: list[Any]) -> None:
            self._rows = rows

        def scalar_one(self) -> Any:
            return self._rows[0] if self._rows else None

        def one(self) -> Any:
            return self._rows[0]

        def all(self) -> list[Any]:
            return self._rows

        def scalars(self) -> _MockResult:
            return self

        def first(self) -> Any | None:
            return self._rows[0] if self._rows else None

    class _MockSession:
        async def execute(self, *_args: Any, **_kwargs: Any) -> _MockResult:
            idx = call_count[0]
            call_count[0] += 1
            data = execute_side_effects[idx]
            return _MockResult(data)

        async def commit(self) -> None:
            pass

        async def refresh(self, *_args: Any) -> None:
            pass

        def add(self, *_args: Any) -> None:
            pass

        async def __aenter__(self) -> _MockSession:
            return self

        async def __aexit__(self, *_: Any) -> None:
            pass

    def factory() -> _MockSession:
        return _MockSession()

    return factory


@pytest.mark.asyncio
async def test_failure_reason_distribution_returns_dict() -> None:
    Row = MagicMock
    row1 = Row()
    row1.failure_reason = "wrong_skill_selected"
    row1.cnt = 5
    row2 = Row()
    row2.failure_reason = "too_slow"
    row2.cnt = 2

    # failure_reason_distribution makes one execute() call
    factory = _make_session_factory([[row1, row2]])
    aggregator = FeedbackAggregator(session_factory=factory)
    dist = await aggregator.failure_reason_distribution()

    assert dist == {"wrong_skill_selected": 5, "too_slow": 2}


@pytest.mark.asyncio
async def test_implicit_signal_distribution_aggregates_in_python() -> None:
    # Each row is a tuple (implicit_signals_list,)
    rows = [
        (["clicked_dashboard", "retried_immediately"],),
        (["clicked_dashboard"],),
        (["abandoned_workflow"],),
    ]

    factory = _make_session_factory([rows])
    aggregator = FeedbackAggregator(session_factory=factory)
    dist = await aggregator.implicit_signal_distribution()

    assert dist["clicked_dashboard"] == 2
    assert dist["retried_immediately"] == 1
    assert dist["abandoned_workflow"] == 1


@pytest.mark.asyncio
async def test_low_rated_run_ids_returns_uuids() -> None:
    id1 = uuid.uuid4()
    id2 = uuid.uuid4()

    Row = MagicMock
    row1 = Row()
    row1.run_id = id1
    row2 = Row()
    row2.run_id = id2

    factory = _make_session_factory([[row1, row2]])
    aggregator = FeedbackAggregator(session_factory=factory)
    result = await aggregator.low_rated_run_ids(limit=10)

    assert result == [id1, id2]
