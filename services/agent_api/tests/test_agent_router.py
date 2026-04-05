"""
Tests for the Agent Platform API routers.

Uses httpx.AsyncClient + ASGITransport; the RunStore is mocked — no real DB required.
"""

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from contracts.run import Run, RunState


# ─────────────────────────────────────────────────────────────────
# Helpers / fixtures
# ─────────────────────────────────────────────────────────────────

def _make_run(
    state: RunState = RunState.CREATED,
    selected_skill: str | None = None,
    error_message: str | None = None,
) -> Run:
    now = datetime.now(UTC)
    return Run(
        run_id=uuid.uuid4(),
        user_id="user-123",
        interface="api",
        request_text="show me revenue",
        state=state,
        selected_skill=selected_skill,
        error_message=error_message,
        created_at=now,
        updated_at=now,
    )


def _make_mock_run_store(run: Run | None = None) -> MagicMock:
    store = MagicMock()
    store.create = AsyncMock(return_value=run or _make_run())
    store.get = AsyncMock(return_value=run or _make_run())
    store.update_state = AsyncMock(return_value=run or _make_run(state=RunState.CANCELLED))
    store.list_for_user = AsyncMock(return_value=[run or _make_run()])
    return store


@pytest.fixture
def app_with_mock_store():
    """Return a FastAPI app instance with RunStore and container dependencies overridden."""
    from agent_api.main import app
    from agent_api.dependencies import get_run_store, get_settings
    from agent_api.config import Settings

    mock_store = _make_mock_run_store()

    mock_settings = MagicMock(spec=Settings)
    mock_settings.environment = "test"
    mock_settings.database_url = "postgresql+asyncpg://test/test"
    mock_settings.log_level = "INFO"

    # Stub the container on app.state so the ask endpoint can read router/orchestrator
    mock_container = MagicMock()
    mock_container.router.route = AsyncMock(
        return_value=MagicMock(
            requires_clarification=False,
            skill_name="answer_business_question",
        )
    )
    mock_container.orchestrator.execute_run = AsyncMock(return_value=None)
    app.state.container = mock_container

    app.dependency_overrides[get_run_store] = lambda: mock_store
    app.dependency_overrides[get_settings] = lambda: mock_settings

    yield app, mock_store

    app.dependency_overrides.clear()
    # Clean up state so other tests are unaffected
    if hasattr(app.state, "container"):
        del app.state.container


# ─────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ask_returns_202_with_run_id(app_with_mock_store):
    app, mock_store = app_with_mock_store
    run = _make_run()
    mock_store.create = AsyncMock(return_value=run)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/agent/ask",
            json={"request_text": "show me revenue"},
            headers={"X-User-Id": "user-123"},
        )

    assert response.status_code == 202
    body = response.json()
    assert body["run_id"] == str(run.run_id)
    assert body["state"] == "created"


@pytest.mark.asyncio
async def test_ask_missing_user_id_returns_401(app_with_mock_store):
    app, _ = app_with_mock_store

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/agent/ask",
            json={"request_text": "show me revenue"},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_run_returns_correct_state(app_with_mock_store):
    app, mock_store = app_with_mock_store
    run = _make_run(state=RunState.ROUTED, selected_skill="answer_business_question")
    mock_store.get = AsyncMock(return_value=run)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            f"/runs/{run.run_id}",
            headers={"X-User-Id": "user-123"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == str(run.run_id)
    assert body["state"] == "routed"
    assert body["selected_skill"] == "answer_business_question"


@pytest.mark.asyncio
async def test_cancel_run_transitions_to_cancelled(app_with_mock_store):
    app, mock_store = app_with_mock_store
    run = _make_run(state=RunState.CREATED)
    cancelled_run = _make_run(state=RunState.CANCELLED)
    cancelled_run = Run(
        **{**cancelled_run.model_dump(), "run_id": run.run_id, "state": RunState.CANCELLED}
    )
    mock_store.get = AsyncMock(return_value=run)
    mock_store.update_state = AsyncMock(return_value=cancelled_run)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/runs/{run.run_id}/cancel",
            headers={"X-User-Id": "user-123"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "cancelled"
    mock_store.update_state.assert_awaited_once_with(run.run_id, RunState.CANCELLED)


@pytest.mark.asyncio
async def test_health_returns_200(app_with_mock_store):
    app, _ = app_with_mock_store

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
