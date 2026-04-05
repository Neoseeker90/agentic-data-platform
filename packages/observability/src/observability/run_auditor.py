"""RunAuditor — concrete implementation of the RunAuditor protocol."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Callable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.db.models import (
    ContextPackORM,
    ExecutionResultORM,
    PlanORM,
    ValidationResultORM,
)
from contracts.context_pack import ContextPack
from contracts.execution import ExecutionResult
from contracts.plan import BasePlan
from contracts.run import Run
from contracts.validation import ValidationResult

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_CONTEXT_PACK_S3_SOURCE_THRESHOLD = 10


class RunAuditor:
    """Concrete implementation of the RunAuditor protocol from skill_sdk.lifecycle.

    Persists audit records for each lifecycle stage of a Run using SQLAlchemy
    async sessions. Optionally archives large context packs to S3 via an
    ``artifact_store``.
    """

    def __init__(
        self,
        session_factory: Callable[..., AsyncSession],
        artifact_store: object = None,
    ) -> None:
        self._session_factory = session_factory
        self._artifact_store = artifact_store

    # ------------------------------------------------------------------
    # Protocol methods
    # ------------------------------------------------------------------

    async def record_plan(self, run: Run, plan: BasePlan) -> None:
        """Upsert a PlanORM row (plan_id as PK)."""
        async with self._session_factory() as session:
            stmt = (
                pg_insert(PlanORM)
                .values(
                    plan_id=plan.plan_id,
                    run_id=plan.run_id,
                    skill_name=plan.skill_name,
                    intent_summary=plan.intent_summary,
                    extracted_entities=plan.extracted_entities,
                    prompt_version_id=plan.prompt_version_id,
                    model_id=plan.model_id,
                    planned_at=plan.planned_at,
                )
                .on_conflict_do_update(
                    index_elements=["plan_id"],
                    set_={
                        "intent_summary": plan.intent_summary,
                        "extracted_entities": plan.extracted_entities,
                        "prompt_version_id": plan.prompt_version_id,
                        "model_id": plan.model_id,
                    },
                )
            )
            await session.execute(stmt)
            await session.commit()
            logger.debug("record_plan run_id=%s plan_id=%s", run.run_id, plan.plan_id)

    async def record_context_pack(self, run: Run, context_pack: ContextPack) -> None:
        """Insert a ContextPackORM row.

        If an ``artifact_store`` is configured and the pack has more than
        :data:`_CONTEXT_PACK_S3_SOURCE_THRESHOLD` sources, the full JSON is
        also archived to S3.
        """
        artifact_key: str | None = context_pack.artifact_key

        if (
            self._artifact_store is not None
            and len(context_pack.sources) > _CONTEXT_PACK_S3_SOURCE_THRESHOLD
        ):
            try:
                artifact_key = await self._artifact_store.store_json(
                    run_id=str(run.run_id),
                    artifact_type="context_pack",
                    data=context_pack.model_dump(mode="json"),
                )
                logger.debug(
                    "Archived context_pack to S3 key=%s run_id=%s",
                    artifact_key,
                    run.run_id,
                )
            except Exception:
                logger.exception(
                    "Failed to archive context_pack to S3 for run_id=%s", run.run_id
                )

        async with self._session_factory() as session:
            session.add(
                ContextPackORM(
                    pack_id=context_pack.pack_id,
                    run_id=context_pack.run_id,
                    plan_id=context_pack.plan_id,
                    skill_name=context_pack.skill_name,
                    sources=[s.model_dump(mode="json") for s in context_pack.sources],
                    unresolved_ambiguities=context_pack.unresolved_ambiguities,
                    token_estimate=context_pack.token_estimate,
                    artifact_key=artifact_key,
                    built_at=context_pack.built_at,
                )
            )
            await session.commit()
            logger.debug(
                "record_context_pack run_id=%s pack_id=%s",
                run.run_id,
                context_pack.pack_id,
            )

    async def record_validation_result(
        self, run: Run, result: ValidationResult
    ) -> None:
        """Insert a ValidationResultORM row."""
        async with self._session_factory() as session:
            session.add(
                ValidationResultORM(
                    result_id=result.result_id,
                    run_id=result.run_id,
                    plan_id=result.plan_id,
                    passed=result.passed,
                    checks=[c.model_dump(mode="json") for c in result.checks],
                    risk_level=result.risk_level,
                    requires_approval=result.requires_approval,
                    validated_at=result.validated_at,
                )
            )
            await session.commit()
            logger.debug(
                "record_validation_result run_id=%s result_id=%s passed=%s",
                run.run_id,
                result.result_id,
                result.passed,
            )

    async def record_execution_result(
        self, run: Run, result: ExecutionResult
    ) -> None:
        """Insert an ExecutionResultORM row."""
        async with self._session_factory() as session:
            session.add(
                ExecutionResultORM(
                    result_id=result.result_id,
                    run_id=result.run_id,
                    plan_id=result.plan_id,
                    success=result.success,
                    output=result.output,
                    formatted_response=result.formatted_response,
                    artifacts=[a.model_dump(mode="json") for a in result.artifacts],
                    llm_call_ids=[str(uid) for uid in result.llm_call_ids],
                    executed_at=result.executed_at,
                )
            )
            await session.commit()
            logger.debug(
                "record_execution_result run_id=%s result_id=%s success=%s",
                run.run_id,
                result.result_id,
                result.success,
            )

    async def record_final_response(self, run: Run, formatted: str) -> None:
        """Update ExecutionResultORM.formatted_response for this run's latest row."""
        async with self._session_factory() as session:
            stmt = (
                select(ExecutionResultORM)
                .where(ExecutionResultORM.run_id == run.run_id)
                .order_by(ExecutionResultORM.executed_at.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if row is None:
                logger.warning(
                    "record_final_response: no ExecutionResultORM found for run_id=%s",
                    run.run_id,
                )
                return
            row.formatted_response = formatted
            await session.commit()
            logger.debug(
                "record_final_response run_id=%s result_id=%s",
                run.run_id,
                row.result_id,
            )
