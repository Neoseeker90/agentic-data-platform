import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.db.engine import get_db
from agent_api.db.models import FeedbackORM
from agent_api.dependencies import CurrentUser
from agent_api.schemas.requests import ExplicitFeedbackRequest, ImplicitSignalRequest
from agent_api.schemas.responses import FeedbackResponse

router = APIRouter()

DBSession = Annotated[AsyncSession, Depends(get_db)]


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
