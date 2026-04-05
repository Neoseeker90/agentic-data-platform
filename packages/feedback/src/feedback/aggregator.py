from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.db.models import FeedbackORM


@dataclass
class SkillRatingSummary:
    total_feedback: int
    avg_score: float | None
    helpful_rate: float | None  # fraction of helpful=True among non-null
    low_rated_count: int  # score <= 2


class FeedbackAggregator:
    def __init__(self, session_factory: Callable[..., Any]) -> None:
        self._session_factory = session_factory

    async def overall_summary(self) -> SkillRatingSummary:
        async with self._session_factory() as session:
            session: AsyncSession  # type: ignore

            total_result = await session.execute(select(func.count()).select_from(FeedbackORM))
            total: int = total_result.scalar_one()

            avg_result = await session.execute(select(func.avg(FeedbackORM.score)))
            avg_score_raw = avg_result.scalar_one()
            avg_score: float | None = float(avg_score_raw) if avg_score_raw is not None else None

            helpful_result = await session.execute(
                select(
                    func.count().filter(FeedbackORM.helpful.is_(True)).label("helpful_true"),
                    func.count(FeedbackORM.helpful).label("helpful_non_null"),
                )
            )
            helpful_row = helpful_result.one()
            helpful_rate: float | None = None
            if helpful_row.helpful_non_null > 0:
                helpful_rate = helpful_row.helpful_true / helpful_row.helpful_non_null

            low_result = await session.execute(
                select(func.count()).select_from(FeedbackORM).where(FeedbackORM.score <= 2)
            )
            low_rated_count: int = low_result.scalar_one()

        return SkillRatingSummary(
            total_feedback=total,
            avg_score=avg_score,
            helpful_rate=helpful_rate,
            low_rated_count=low_rated_count,
        )

    async def failure_reason_distribution(self) -> dict[str, int]:
        async with self._session_factory() as session:
            session: AsyncSession  # type: ignore
            result = await session.execute(
                select(FeedbackORM.failure_reason, func.count().label("cnt"))
                .where(FeedbackORM.failure_reason.isnot(None))
                .group_by(FeedbackORM.failure_reason)
            )
            return {row.failure_reason: row.cnt for row in result.all()}

    async def implicit_signal_distribution(self) -> dict[str, int]:
        async with self._session_factory() as session:
            session: AsyncSession  # type: ignore
            result = await session.execute(
                select(FeedbackORM.implicit_signals).where(
                    FeedbackORM.implicit_signals != []  # noqa: PLC1901
                )
            )
            counts: dict[str, int] = {}
            for (signals,) in result.all():
                for signal in signals or []:
                    counts[signal] = counts.get(signal, 0) + 1
            return counts

    async def low_rated_run_ids(self, limit: int = 50) -> list[UUID]:
        async with self._session_factory() as session:
            session: AsyncSession  # type: ignore
            result = await session.execute(
                select(FeedbackORM.run_id)
                .where(FeedbackORM.score <= 2)
                .order_by(FeedbackORM.captured_at.desc())
                .limit(limit)
            )
            return [row.run_id for row in result.all()]
