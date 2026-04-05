from __future__ import annotations

import logging
import random
from collections.abc import Callable
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.db.models import ExecutionResultORM, FeedbackORM, RunORM
from contracts.evaluation import EvaluationCase
from contracts.feedback import FeedbackFailureReason
from contracts.run import RunState

logger = logging.getLogger(__name__)


def derive_tags(
    run: RunORM,
    feedback: FeedbackORM | None,
) -> list[str]:
    tags: list[str] = []

    if run.selected_skill:
        tags.append(run.selected_skill)

    if feedback is not None:
        reason = feedback.failure_reason
        if reason == FeedbackFailureReason.WRONG_SKILL_SELECTED:
            tags.append("routing")
        if reason in {
            FeedbackFailureReason.MISSING_CONTEXT,
            FeedbackFailureReason.WRONG_METRIC_OR_DASHBOARD,
        }:
            tags.append("context_quality")

        if feedback.score is not None:
            tags.append("has_feedback")
            if feedback.score <= 2:
                tags.append("low_rated")

    return tags


class EvalCaseGenerator:
    def __init__(self, session_factory: Callable[..., Any]) -> None:
        self._session_factory = session_factory

    async def generate_from_run(self, run_id: UUID) -> EvaluationCase | None:
        async with self._session_factory() as session:
            session: AsyncSession

            run_result = await session.execute(
                select(RunORM).where(RunORM.run_id == run_id)
            )
            run = run_result.scalar_one_or_none()
            if run is None:
                logger.warning("Run %s not found", run_id)
                return None

            feedback_result = await session.execute(
                select(FeedbackORM)
                .where(FeedbackORM.run_id == run_id)
                .order_by(FeedbackORM.captured_at.desc())
                .limit(1)
            )
            feedback = feedback_result.scalar_one_or_none()

            if feedback is None:
                return None

            exec_result = await session.execute(
                select(ExecutionResultORM)
                .where(ExecutionResultORM.run_id == run_id)
                .order_by(ExecutionResultORM.executed_at.desc())
                .limit(1)
            )
            exec_row = exec_result.scalar_one_or_none()

            observed_response: str | None = None
            if exec_row is not None:
                observed_response = exec_row.formatted_response

            failure_reason: FeedbackFailureReason | None = None
            if feedback.failure_reason is not None:
                try:
                    failure_reason = FeedbackFailureReason(feedback.failure_reason)
                except ValueError:
                    logger.warning(
                        "Unknown failure_reason %r for run %s", feedback.failure_reason, run_id
                    )

            expected_skill: str | None = run.selected_skill
            if failure_reason == FeedbackFailureReason.WRONG_SKILL_SELECTED:
                expected_skill = None

            tags = derive_tags(run, feedback)

            return EvaluationCase(
                source_run_id=run_id,
                request_text=run.request_text,
                expected_skill=expected_skill,
                observed_skill=run.selected_skill,
                observed_response=observed_response,
                feedback_score=feedback.score,
                feedback_failure_reason=failure_reason,
                dataset_tags=tags,
                created_by="auto",
            )

    async def generate_batch_from_low_rated(
        self,
        score_threshold: int = 2,
        limit: int = 50,
    ) -> list[EvaluationCase]:
        async with self._session_factory() as session:
            session: AsyncSession
            result = await session.execute(
                select(FeedbackORM.run_id)
                .where(FeedbackORM.score <= score_threshold)
                .order_by(FeedbackORM.captured_at.desc())
                .limit(limit)
            )
            run_ids = [row.run_id for row in result.all()]

        cases: list[EvaluationCase] = []
        for run_id in run_ids:
            case = await self.generate_from_run(run_id)
            if case is not None:
                cases.append(case)
        return cases

    async def generate_batch_sampled(
        self,
        sample_rate: float = 0.05,
        limit: int = 100,
    ) -> list[EvaluationCase]:
        async with self._session_factory() as session:
            session: AsyncSession
            result = await session.execute(
                select(RunORM.run_id)
                .where(RunORM.state == RunState.SUCCEEDED)
                .order_by(RunORM.created_at.desc())
                .limit(limit * 20)
            )
            all_run_ids = [row.run_id for row in result.all()]

        sampled = [rid for rid in all_run_ids if random.random() < sample_rate]
        sampled = sampled[:limit]

        cases: list[EvaluationCase] = []
        for run_id in sampled:
            async with self._session_factory() as session:
                session: AsyncSession

                run_result = await session.execute(
                    select(RunORM).where(RunORM.run_id == run_id)
                )
                run = run_result.scalar_one_or_none()
                if run is None:
                    continue

                exec_result = await session.execute(
                    select(ExecutionResultORM)
                    .where(ExecutionResultORM.run_id == run_id)
                    .order_by(ExecutionResultORM.executed_at.desc())
                    .limit(1)
                )
                exec_row = exec_result.scalar_one_or_none()

                observed_response: str | None = None
                if exec_row is not None:
                    observed_response = exec_row.formatted_response

                tags = derive_tags(run, None)

                cases.append(
                    EvaluationCase(
                        source_run_id=run_id,
                        request_text=run.request_text,
                        expected_skill=run.selected_skill,
                        observed_skill=run.selected_skill,
                        observed_response=observed_response,
                        feedback_score=None,
                        feedback_failure_reason=None,
                        dataset_tags=tags,
                        created_by="auto",
                    )
                )
        return cases
