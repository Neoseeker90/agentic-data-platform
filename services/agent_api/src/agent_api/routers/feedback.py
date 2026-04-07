from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.db.engine import get_db, get_session_factory
from agent_api.db.models import EvaluationCaseORM, ExecutionResultORM, FeedbackORM, RunORM
from agent_api.dependencies import CurrentUser
from agent_api.schemas.requests import ExplicitFeedbackRequest, ImplicitSignalRequest
from agent_api.schemas.responses import FeedbackResponse

logger = logging.getLogger(__name__)

router = APIRouter()

DBSession = Annotated[AsyncSession, Depends(get_db)]


async def _maybe_create_eval_case(
    run_id: uuid.UUID,
    failure_reason: str | None,
    comment: str | None,
    expected_skill: str | None = None,
    error_label: str | None = None,
) -> None:
    """Background task: if the user gave a thumbs-down, snapshot the run as a failing eval case."""
    try:
        async with get_session_factory()() as session:
            # Fetch the run
            run_row = (
                await session.execute(select(RunORM).where(RunORM.run_id == run_id))
            ).scalar_one_or_none()
            if run_row is None:
                return

            # Fetch the latest execution result (formatted response)
            exec_row = (
                await session.execute(
                    select(ExecutionResultORM)
                    .where(ExecutionResultORM.run_id == run_id)
                    .order_by(ExecutionResultORM.executed_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

            observed_response = exec_row.formatted_response if exec_row else None

            # Avoid duplicates — skip if an auto case already exists for this run
            existing = (
                await session.execute(
                    select(EvaluationCaseORM)
                    .where(EvaluationCaseORM.source_run_id == run_id)
                    .where(EvaluationCaseORM.created_by == "auto")
                    .limit(1)
                )
            ).scalar_one_or_none()
            if existing is not None:
                return

            now = datetime.now(UTC)
            # Build dataset tags — include error_label if provided
            tags = ["auto", "thumbs_down"]
            if error_label:
                tags.append(error_label)

            case = EvaluationCaseORM(
                case_id=uuid.uuid4(),
                source_run_id=run_id,
                request_text=run_row.request_text,
                expected_skill=expected_skill,  # populated from in-chat label
                expected_asset_refs=[],
                observed_skill=run_row.selected_skill,
                observed_response=observed_response,
                feedback_score=None,
                feedback_failure_reason=failure_reason,
                human_label=error_label,  # "wrong_skill"|"wrong_query"|"incomplete"|"hallucination"
                dataset_tags=tags,
                status="failing",
                created_by="auto",
                created_at=now,
                updated_at=now,
            )
            session.add(case)
            await session.commit()
            logger.info("Created eval case %s from thumbs-down on run %s", case.case_id, run_id)
    except Exception:
        logger.warning("Failed to create eval case for run %s", run_id, exc_info=True)


@router.post("/{run_id}", status_code=status.HTTP_201_CREATED, response_model=FeedbackResponse)
async def submit_feedback(
    run_id: uuid.UUID,
    body: ExplicitFeedbackRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> FeedbackResponse:
    feedback_id = uuid.uuid4()
    orm = FeedbackORM(
        feedback_id=feedback_id,
        run_id=run_id,
        user_id=current_user.user_id,
        helpful=body.helpful,
        score=body.score,
        comment=body.comment,
        failure_reason=body.failure_reason.value if body.failure_reason else None,
        implicit_signals=[],
        captured_at=datetime.now(UTC),
    )
    db.add(orm)
    await db.commit()

    # If thumbs-down, snapshot this run as a failing eval case in the background
    if body.helpful is False:
        failure_reason = body.failure_reason.value if body.failure_reason else None
        asyncio.create_task(
            _maybe_create_eval_case(
                run_id,
                failure_reason,
                body.comment,
                expected_skill=body.expected_skill,
                error_label=body.error_label,
            )
        )

    return FeedbackResponse(feedback_id=feedback_id, run_id=run_id)


@router.post(
    "/{run_id}/signal",
    status_code=status.HTTP_201_CREATED,
    response_model=FeedbackResponse,
)
async def submit_implicit_signal(
    run_id: uuid.UUID,
    body: ImplicitSignalRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> FeedbackResponse:
    feedback_id = uuid.uuid4()
    orm = FeedbackORM(
        feedback_id=feedback_id,
        run_id=run_id,
        user_id=current_user.user_id,
        helpful=None,
        score=None,
        comment=None,
        failure_reason=None,
        implicit_signals=[body.signal.value],
        captured_at=datetime.now(UTC),
    )
    db.add(orm)
    await db.commit()
    return FeedbackResponse(feedback_id=feedback_id, run_id=run_id)
