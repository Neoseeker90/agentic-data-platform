import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.db.models import ExecutionResultORM
from agent_api.db.run_store import RunStore
from agent_api.dependencies import CurrentUser, get_db_session, get_run_store
from agent_api.schemas.requests import ApprovalRequest
from agent_api.schemas.responses import RunStatusResponse
from contracts.run import TERMINAL_STATES, RunState

router = APIRouter()


def _run_to_response(run, response: str | None = None) -> RunStatusResponse:
    return RunStatusResponse(
        run_id=run.run_id,
        state=str(run.state),
        selected_skill=run.selected_skill,
        created_at=run.created_at,
        updated_at=run.updated_at,
        error_message=run.error_message,
        response=response,
    )


async def _fetch_response(session: AsyncSession, run_id: uuid.UUID) -> str | None:
    stmt = (
        select(ExecutionResultORM.formatted_response)
        .where(ExecutionResultORM.run_id == run_id)
        .order_by(ExecutionResultORM.executed_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


@router.get("/{run_id}", response_model=RunStatusResponse)
async def get_run(
    run_id: uuid.UUID,
    current_user: CurrentUser,
    run_store: Annotated[RunStore, Depends(get_run_store)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> RunStatusResponse:
    run = await run_store.get(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    response = None
    if str(run.state) == RunState.SUCCEEDED:
        response = await _fetch_response(session, run_id)
    return _run_to_response(run, response)


@router.post("/{run_id}/approve", response_model=RunStatusResponse)
async def approve_run(
    run_id: uuid.UUID,
    body: ApprovalRequest,
    current_user: CurrentUser,
    run_store: Annotated[RunStore, Depends(get_run_store)],
) -> RunStatusResponse:
    run = await run_store.get(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    if RunState(run.state) in TERMINAL_STATES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run is already in terminal state: {run.state}",
        )

    if body.decision == "approved":
        run = await run_store.update_state(run_id, RunState.EXECUTING)
    else:
        run = await run_store.update_state(run_id, RunState.CANCELLED)

    return _run_to_response(run)


@router.post("/{run_id}/cancel", response_model=RunStatusResponse)
async def cancel_run(
    run_id: uuid.UUID,
    current_user: CurrentUser,
    run_store: Annotated[RunStore, Depends(get_run_store)],
) -> RunStatusResponse:
    run = await run_store.get(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    if RunState(run.state) in TERMINAL_STATES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run is already in terminal state: {run.state}",
        )

    run = await run_store.update_state(run_id, RunState.CANCELLED)
    return _run_to_response(run)
