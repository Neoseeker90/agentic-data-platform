from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.db.models import ExecutionResultORM
from agent_api.db.run_store import RunStore
from agent_api.db.session_store import SessionStore
from agent_api.dependencies import (
    CurrentUser,
    get_auditor,
    get_orchestrator,
    get_platform_router,
    get_run_store,
    get_session_store,
)
from agent_api.schemas.requests import AskRequest, ClarificationRequest
from agent_api.schemas.responses import AskResponse
from contracts.run import RunState
from skill_sdk.conversation import build_contextual_request

logger = logging.getLogger(__name__)

router = APIRouter()

_MAX_RESPONSE_CHARS = 800  # chars of assistant response saved to session history


async def _fetch_formatted_response(session: AsyncSession, run_id: uuid.UUID) -> str | None:
    stmt = (
        select(ExecutionResultORM.formatted_response)
        .where(ExecutionResultORM.run_id == run_id)
        .order_by(ExecutionResultORM.executed_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _save_assistant_turn(
    session_store: SessionStore,
    session_id: uuid.UUID,
    run_id: uuid.UUID,
    run_store: RunStore,
) -> None:
    """After execution, save the assistant's response (or question) as a session turn."""
    from agent_api.db.engine import get_db  # noqa: PLC0415

    run = await run_store.get(run_id)
    if run is None:
        return

    state = RunState(run.state) if run.state in RunState.__members__.values() else None

    if state == RunState.AWAITING_SKILL_CLARIFICATION:
        content = f"[Needs clarification] {run.error_message or '?'}"
    elif state == RunState.AWAITING_APPROVAL:
        content = "[Awaiting approval before executing]"
    elif state == RunState.FAILED:
        content = f"[Error] {run.error_message or 'unknown error'}"
    elif state == RunState.CANCELLED:
        content = "[Run was cancelled]"
    else:
        # Fetch actual formatted response from execution_results table
        content = None
        async for db_session in get_db():
            content = await _fetch_formatted_response(db_session, run_id)
            break
        content = (content or "(no response)")[:_MAX_RESPONSE_CHARS]

    await session_store.save_turn(
        session_id=session_id,
        role="assistant",
        content=content,
        run_id=run_id,
    )


async def _route_and_execute(
    run,
    platform_router,
    run_store: RunStore,
    orchestrator,
    session_id: uuid.UUID,
    session_store: SessionStore,
    auditor=None,
) -> None:
    """Background task: route the run then execute it, then persist the assistant turn."""
    try:
        decision = await platform_router.route(run)

        if auditor is not None:
            try:
                await auditor.record_route_decision(decision)
            except Exception:
                logger.warning("Failed to persist route decision for run_id=%s", run.run_id, exc_info=True)

        if decision.requires_clarification:
            await run_store.update_state(
                str(run.run_id),
                RunState.CREATED,
                error_message=decision.clarification_message,
            )
            logger.info(
                "Run %s needs router clarification: %s", run.run_id, decision.clarification_message
            )
            await session_store.save_turn(
                session_id=session_id,
                role="assistant",
                content=f"[Needs clarification] {decision.clarification_message}",
                run_id=run.run_id,
            )
            return

        run = await run_store.update_state(
            str(run.run_id),
            RunState.ROUTED,
            selected_skill=decision.skill_name,
        )
        await orchestrator.execute_run(run)

    except Exception:
        logger.exception("Background orchestration failed for run_id=%s", run.run_id)
    finally:
        try:
            await _save_assistant_turn(session_store, session_id, run.run_id, run_store)
        except Exception:
            logger.warning("Failed to save assistant turn for run_id=%s", run.run_id, exc_info=True)


@router.post("/ask", status_code=status.HTTP_202_ACCEPTED, response_model=AskResponse)
async def ask(
    body: AskRequest,
    request: Request,
    current_user: CurrentUser,
    run_store: Annotated[RunStore, Depends(get_run_store)],
    session_store: Annotated[SessionStore, Depends(get_session_store)],
) -> AskResponse:
    session_id = body.session_id or uuid.uuid4()

    # Load prior turns and build context-aware request text
    history = await session_store.get_history(session_id)
    contextual_request = build_contextual_request(body.request_text, history)

    run = await run_store.create(
        user_id=current_user.user_id,
        interface=body.interface,
        request_text=contextual_request,
    )

    # Persist the user's original (non-augmented) message into the session
    await session_store.save_turn(
        session_id=session_id,
        role="user",
        content=body.request_text,
        run_id=run.run_id,
    )

    platform_router = get_platform_router(request)
    orchestrator = get_orchestrator(request)
    auditor = get_auditor(request)
    asyncio.create_task(
        _route_and_execute(run, platform_router, run_store, orchestrator, session_id, session_store, auditor)
    )
    return AskResponse(run_id=run.run_id, state=str(run.state), session_id=session_id)


@router.post("/runs/{run_id}/clarification", response_model=AskResponse)
async def submit_clarification(
    run_id: uuid.UUID,
    body: ClarificationRequest,
    request: Request,
    current_user: CurrentUser,
    run_store: Annotated[RunStore, Depends(get_run_store)],
    session_store: Annotated[SessionStore, Depends(get_session_store)],
) -> AskResponse:
    run = await run_store.get(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    current_state = run.state
    if current_state not in (RunState.CREATED, RunState.AWAITING_SKILL_CLARIFICATION):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run is in state '{current_state}' and cannot accept clarification",
        )

    # Recover the session_id from the original run's turn (fall back to new session)
    session_id = await session_store.get_session_id_for_run(run_id) or uuid.uuid4()

    # Load full session history and append the clarification as additional context
    history = await session_store.get_history(session_id)
    augmented = f"{run.request_text}\n\nUser clarification: {body.response}"
    contextual_request = build_contextual_request(augmented, history)

    new_run = await run_store.create(
        user_id=current_user.user_id,
        interface=run.interface,
        request_text=contextual_request,
    )

    await session_store.save_turn(
        session_id=session_id,
        role="user",
        content=body.response,
        run_id=new_run.run_id,
    )

    platform_router = get_platform_router(request)
    orchestrator = get_orchestrator(request)
    auditor = get_auditor(request)
    asyncio.create_task(
        _route_and_execute(
            new_run, platform_router, run_store, orchestrator, session_id, session_store, auditor
        )
    )
    return AskResponse(run_id=new_run.run_id, state=str(new_run.state), session_id=session_id)
