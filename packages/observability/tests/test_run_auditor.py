"""Unit tests for RunAuditor and PromptVersionRegistry."""

from __future__ import annotations

import hashlib
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from contracts.context_pack import ContextPack, ContextSource, SourceAuthority, SourceType
from contracts.execution import ExecutionResult
from contracts.plan import BasePlan
from contracts.run import Run, RunState
from contracts.validation import ValidationResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session_factory(session: MagicMock):
    """Return an async context-manager factory wrapping *session*."""

    @asynccontextmanager
    async def factory():
        yield session

    return factory


def _make_run() -> Run:
    return Run(
        run_id=uuid4(),
        user_id="user-1",
        interface="slack",
        request_text="What is ARR?",
        state=RunState.PLANNED,
    )


def _make_plan(run: Run) -> BasePlan:
    return BasePlan(
        plan_id=uuid4(),
        run_id=run.run_id,
        skill_name="answer_business_question",
        intent_summary="User wants ARR figure.",
    )


# ---------------------------------------------------------------------------
# RunAuditor tests
# ---------------------------------------------------------------------------


class TestRunAuditor:
    @pytest.mark.asyncio
    async def test_record_plan_persists_orm_row(self) -> None:
        """record_plan should call session.execute (upsert) and commit."""
        from observability.run_auditor import RunAuditor

        session = AsyncMock()
        # execute returns an object; we only care that it's called
        session.execute = AsyncMock(return_value=MagicMock())

        factory = _make_session_factory(session)
        auditor = RunAuditor(session_factory=factory)

        run = _make_run()
        plan = _make_plan(run)

        await auditor.record_plan(run, plan)

        session.execute.assert_awaited_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_record_validation_result(self) -> None:
        """record_validation_result should call session.add with ValidationResultORM."""
        from agent_api.db.models import ValidationResultORM
        from observability.run_auditor import RunAuditor

        session = AsyncMock()
        factory = _make_session_factory(session)
        auditor = RunAuditor(session_factory=factory)

        run = _make_run()
        plan = _make_plan(run)
        result = ValidationResult(
            run_id=run.run_id,
            plan_id=plan.plan_id,
            passed=True,
            risk_level="low",
        )

        await auditor.record_validation_result(run, result)

        session.add.assert_called_once()
        added_obj = session.add.call_args[0][0]
        assert isinstance(added_obj, ValidationResultORM)
        assert added_obj.passed is True
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_record_context_pack_no_artifact_store(self) -> None:
        """No artifact_store → DB insert only, no S3 call."""
        from agent_api.db.models import ContextPackORM
        from observability.run_auditor import RunAuditor

        session = AsyncMock()
        factory = _make_session_factory(session)
        auditor = RunAuditor(session_factory=factory, artifact_store=None)

        run = _make_run()
        plan = _make_plan(run)
        pack = ContextPack(
            run_id=run.run_id,
            plan_id=plan.plan_id,
            skill_name="answer_business_question",
            sources=[],
        )

        await auditor.record_context_pack(run, pack)

        session.add.assert_called_once()
        added_obj = session.add.call_args[0][0]
        assert isinstance(added_obj, ContextPackORM)
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_record_context_pack_with_artifact_store_large_pack(self) -> None:
        """When pack has >10 sources and artifact_store is set, S3 upload is called."""
        from observability.run_auditor import RunAuditor

        session = AsyncMock()
        factory = _make_session_factory(session)

        mock_artifact_store = AsyncMock()
        mock_artifact_store.store_json = AsyncMock(return_value="runs/x/context_pack.json")

        auditor = RunAuditor(session_factory=factory, artifact_store=mock_artifact_store)

        run = _make_run()
        plan = _make_plan(run)

        sources = [
            ContextSource(
                source_type=SourceType.DBT_MODEL,
                authority=SourceAuthority.PRIMARY,
                object_ref=f"model_{i}",
                label=f"Model {i}",
                snippet="...",
            )
            for i in range(11)
        ]
        pack = ContextPack(
            run_id=run.run_id,
            plan_id=plan.plan_id,
            skill_name="answer_business_question",
            sources=sources,
        )

        await auditor.record_context_pack(run, pack)

        mock_artifact_store.store_json.assert_awaited_once()
        session.add.assert_called_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_record_execution_result(self) -> None:
        """record_execution_result should add ExecutionResultORM to session."""
        from agent_api.db.models import ExecutionResultORM
        from observability.run_auditor import RunAuditor

        session = AsyncMock()
        factory = _make_session_factory(session)
        auditor = RunAuditor(session_factory=factory)

        run = _make_run()
        plan = _make_plan(run)
        result = ExecutionResult(
            run_id=run.run_id,
            plan_id=plan.plan_id,
            success=True,
            output={"answer": "ARR is $10M"},
        )

        await auditor.record_execution_result(run, result)

        session.add.assert_called_once()
        added_obj = session.add.call_args[0][0]
        assert isinstance(added_obj, ExecutionResultORM)
        assert added_obj.success is True

    @pytest.mark.asyncio
    async def test_record_final_response_updates_row(self) -> None:
        """record_final_response should update formatted_response on latest row."""
        from observability.run_auditor import RunAuditor

        # Simulate an existing ExecutionResultORM row
        mock_row = MagicMock()
        mock_row.result_id = uuid4()
        mock_row.formatted_response = None

        mock_scalar = MagicMock()
        mock_scalar.scalar_one_or_none.return_value = mock_row

        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_scalar)

        factory = _make_session_factory(session)
        auditor = RunAuditor(session_factory=factory)

        run = _make_run()
        await auditor.record_final_response(run, "ARR is $10M")

        assert mock_row.formatted_response == "ARR is $10M"
        session.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# PromptVersionRegistry tests
# ---------------------------------------------------------------------------


class TestPromptVersionRegistry:
    @pytest.mark.asyncio
    async def test_prompt_version_registry_returns_hash(self) -> None:
        """register_if_new should return a 64-char hex SHA-256 string."""
        from observability.prompt_registry import PromptVersionRegistry

        # scalar_one_or_none returns None → triggers insert path
        mock_scalar = MagicMock()
        mock_scalar.scalar_one_or_none.return_value = None

        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_scalar)

        factory = _make_session_factory(session)
        registry = PromptVersionRegistry(session_factory=factory)

        content = "You are a helpful assistant."
        version_hash = await registry.register_if_new(
            component="router",
            content=content,
            model_id="claude-sonnet-4-6",
            created_by="test-user",
        )

        # Must be a 64-char hex string
        assert isinstance(version_hash, str)
        assert len(version_hash) == 64
        assert all(c in "0123456789abcdef" for c in version_hash)

        # Must match the SHA-256 of the content
        expected = hashlib.sha256(content.encode()).hexdigest()
        assert version_hash == expected

        # A new row should have been added
        session.add.assert_called_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_prompt_version_registry_idempotent(self) -> None:
        """register_if_new should NOT insert a row when hash already exists."""
        from agent_api.db.models import PromptVersionORM
        from observability.prompt_registry import PromptVersionRegistry

        existing_row = MagicMock(spec=PromptVersionORM)
        mock_scalar = MagicMock()
        mock_scalar.scalar_one_or_none.return_value = existing_row

        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_scalar)

        factory = _make_session_factory(session)
        registry = PromptVersionRegistry(session_factory=factory)

        version_hash = await registry.register_if_new(
            component="router",
            content="Same content.",
            model_id="claude-sonnet-4-6",
        )

        # Should still return the hash
        assert len(version_hash) == 64
        # Should NOT call add or commit (no new row)
        session.add.assert_not_called()
        session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_active_prompt_returns_none_when_missing(self) -> None:
        """get_active_prompt returns None when no active row exists."""
        from observability.prompt_registry import PromptVersionRegistry

        mock_scalar = MagicMock()
        mock_scalar.scalar_one_or_none.return_value = None

        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_scalar)

        factory = _make_session_factory(session)
        registry = PromptVersionRegistry(session_factory=factory)

        result = await registry.get_active_prompt("router")
        assert result is None
