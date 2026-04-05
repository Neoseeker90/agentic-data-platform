from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.db.models import FeedbackORM
from contracts.feedback import FeedbackFailureReason, FeedbackRecord, ImplicitSignal


class FeedbackStore:
    def __init__(self, session_factory: Callable[..., Any]) -> None:
        self._session_factory = session_factory

    # ------------------------------------------------------------------
    # Mapping helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_record(orm: FeedbackORM) -> FeedbackRecord:
        return FeedbackRecord(
            feedback_id=orm.feedback_id,
            run_id=orm.run_id,
            user_id=orm.user_id,
            helpful=orm.helpful,
            score=orm.score,
            comment=orm.comment,
            failure_reason=(
                FeedbackFailureReason(orm.failure_reason) if orm.failure_reason else None
            ),
            implicit_signals=[ImplicitSignal(s) for s in (orm.implicit_signals or [])],
            captured_at=orm.captured_at,
        )

    @staticmethod
    def _from_record(record: FeedbackRecord) -> FeedbackORM:
        return FeedbackORM(
            feedback_id=record.feedback_id,
            run_id=record.run_id,
            user_id=record.user_id,
            helpful=record.helpful,
            score=record.score,
            comment=record.comment,
            failure_reason=record.failure_reason.value if record.failure_reason else None,
            implicit_signals=[s.value for s in record.implicit_signals],
            captured_at=record.captured_at,
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def create(self, record: FeedbackRecord) -> FeedbackRecord:
        async with self._session_factory() as session:
            session: AsyncSession  # type: ignore
            orm = self._from_record(record)
            session.add(orm)
            await session.commit()
            await session.refresh(orm)
            return self._to_record(orm)

    async def get_by_run(self, run_id: UUID) -> FeedbackRecord | None:
        async with self._session_factory() as session:
            session: AsyncSession  # type: ignore
            result = await session.execute(select(FeedbackORM).where(FeedbackORM.run_id == run_id))
            orm = result.scalars().first()
            return self._to_record(orm) if orm is not None else None

    async def append_implicit_signal(
        self,
        run_id: UUID,
        user_id: str,
        signal: ImplicitSignal,
    ) -> FeedbackRecord:
        async with self._session_factory() as session:
            session: AsyncSession  # type: ignore
            result = await session.execute(
                select(FeedbackORM).where(
                    FeedbackORM.run_id == run_id,
                    FeedbackORM.user_id == user_id,
                )
            )
            orm = result.scalars().first()

            if orm is not None:
                existing: list[str] = list(orm.implicit_signals or [])
                existing.append(signal.value)
                orm.implicit_signals = existing
                await session.commit()
                await session.refresh(orm)
                return self._to_record(orm)

            # No existing record — create a new minimal one.
            new_record = FeedbackRecord(
                feedback_id=uuid.uuid4(),
                run_id=run_id,
                user_id=user_id,
                implicit_signals=[signal],
                captured_at=datetime.now(UTC),
            )
            new_orm = self._from_record(new_record)
            session.add(new_orm)
            await session.commit()
            await session.refresh(new_orm)
            return self._to_record(new_orm)

    async def list_low_rated(
        self,
        score_threshold: int = 2,
        limit: int = 100,
    ) -> list[FeedbackRecord]:
        async with self._session_factory() as session:
            session: AsyncSession  # type: ignore
            result = await session.execute(
                select(FeedbackORM)
                .where(FeedbackORM.score <= score_threshold)
                .order_by(FeedbackORM.captured_at.desc())
                .limit(limit)
            )
            return [self._to_record(row) for row in result.scalars().all()]

    async def list_with_failure_reason(
        self,
        reason: FeedbackFailureReason,
        limit: int = 100,
    ) -> list[FeedbackRecord]:
        async with self._session_factory() as session:
            session: AsyncSession  # type: ignore
            result = await session.execute(
                select(FeedbackORM)
                .where(FeedbackORM.failure_reason == reason.value)
                .order_by(FeedbackORM.captured_at.desc())
                .limit(limit)
            )
            return [self._to_record(row) for row in result.scalars().all()]

    async def list_recent(self, limit: int = 100) -> list[FeedbackRecord]:
        async with self._session_factory() as session:
            session: AsyncSession  # type: ignore
            result = await session.execute(
                select(FeedbackORM).order_by(FeedbackORM.captured_at.desc()).limit(limit)
            )
            return [self._to_record(row) for row in result.scalars().all()]
