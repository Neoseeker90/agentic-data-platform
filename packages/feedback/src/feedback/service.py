from __future__ import annotations

import uuid
from datetime import UTC, datetime
from uuid import UUID

from contracts.feedback import FeedbackFailureReason, FeedbackRecord, ImplicitSignal
from feedback.db.feedback_store import FeedbackStore


class FeedbackService:
    def __init__(self, store: FeedbackStore) -> None:
        self._store = store

    async def capture_explicit(
        self,
        run_id: UUID,
        user_id: str,
        helpful: bool | None = None,
        score: int | None = None,
        comment: str | None = None,
        failure_reason: FeedbackFailureReason | None = None,
    ) -> FeedbackRecord:
        record = FeedbackRecord(
            feedback_id=uuid.uuid4(),
            run_id=run_id,
            user_id=user_id,
            helpful=helpful,
            score=score,
            comment=comment,
            failure_reason=failure_reason,
            implicit_signals=[],
            captured_at=datetime.now(UTC),
        )
        return await self._store.create(record)

    async def capture_implicit(
        self,
        run_id: UUID,
        user_id: str,
        signal: ImplicitSignal,
    ) -> FeedbackRecord:
        return await self._store.append_implicit_signal(run_id, user_id, signal)
