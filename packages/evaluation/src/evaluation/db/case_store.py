from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any
from uuid import UUID

from sqlalchemy import cast, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.db.models import EvaluationCaseORM
from contracts.evaluation import EvaluationCase
from contracts.feedback import FeedbackFailureReason

logger = logging.getLogger(__name__)


def _orm_to_case(row: EvaluationCaseORM) -> EvaluationCase:
    failure_reason: FeedbackFailureReason | None = None
    if row.feedback_failure_reason is not None:
        try:
            failure_reason = FeedbackFailureReason(row.feedback_failure_reason)
        except ValueError:
            logger.warning(
                "Unknown failure_reason %r in case %s", row.feedback_failure_reason, row.case_id
            )

    return EvaluationCase(
        case_id=row.case_id,
        source_run_id=row.source_run_id,
        request_text=row.request_text,
        expected_skill=row.expected_skill,
        expected_asset_refs=list(row.expected_asset_refs or []),
        observed_skill=row.observed_skill,
        observed_response=row.observed_response,
        feedback_score=row.feedback_score,
        feedback_failure_reason=failure_reason,
        human_label=row.human_label,
        dataset_tags=list(row.dataset_tags or []),
        status=row.status,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _case_to_orm(case: EvaluationCase) -> EvaluationCaseORM:
    return EvaluationCaseORM(
        case_id=case.case_id,
        source_run_id=case.source_run_id,
        request_text=case.request_text,
        expected_skill=case.expected_skill,
        expected_asset_refs=list(case.expected_asset_refs),
        observed_skill=case.observed_skill,
        observed_response=case.observed_response,
        feedback_score=case.feedback_score,
        feedback_failure_reason=(
            case.feedback_failure_reason.value if case.feedback_failure_reason is not None else None
        ),
        human_label=case.human_label,
        dataset_tags=list(case.dataset_tags),
        status=case.status,
        created_by=case.created_by,
        created_at=case.created_at,
        updated_at=case.updated_at,
    )


class CaseStore:
    def __init__(self, session_factory: Callable[..., Any]) -> None:
        self._session_factory = session_factory

    async def save(self, case: EvaluationCase) -> EvaluationCase:
        async with self._session_factory() as session:
            session: AsyncSession  # type: ignore
            row = _case_to_orm(case)
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return _orm_to_case(row)

    async def get(self, case_id: UUID) -> EvaluationCase | None:
        async with self._session_factory() as session:
            session: AsyncSession  # type: ignore
            result = await session.execute(
                select(EvaluationCaseORM).where(EvaluationCaseORM.case_id == case_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return _orm_to_case(row)

    async def list_cases(
        self,
        tags: list[str] | None = None,
        status: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[EvaluationCase]:
        async with self._session_factory() as session:
            session: AsyncSession  # type: ignore
            query = select(EvaluationCaseORM)

            if tags:
                for tag in tags:
                    query = query.where(EvaluationCaseORM.dataset_tags.op("@>")(cast([tag], JSONB)))

            if status is not None:
                query = query.where(EvaluationCaseORM.status == status)

            query = query.order_by(EvaluationCaseORM.created_at.desc()).limit(limit).offset(offset)
            result = await session.execute(query)
            return [_orm_to_case(row) for row in result.scalars().all()]

    async def update_status(self, case_id: UUID, status: str) -> None:
        async with self._session_factory() as session:
            session: AsyncSession  # type: ignore
            result = await session.execute(
                select(EvaluationCaseORM).where(EvaluationCaseORM.case_id == case_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                logger.warning("update_status: case %s not found", case_id)
                return
            row.status = status
            await session.commit()

    async def count(self) -> int:
        async with self._session_factory() as session:
            session: AsyncSession  # type: ignore
            result = await session.execute(select(func.count()).select_from(EvaluationCaseORM))
            return result.scalar_one()
