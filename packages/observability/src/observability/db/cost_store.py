"""CostStore — async SQLAlchemy persistence for TokenCostRecord."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.db.models import TokenCostRecordORM
from contracts.cost import TokenCostRecord


class CostStore:
    """Persists and queries :class:`~contracts.cost.TokenCostRecord` rows."""

    def __init__(self, session_factory: Callable[..., AsyncSession]) -> None:
        self._session_factory = session_factory

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_orm(record: TokenCostRecord) -> TokenCostRecordORM:
        return TokenCostRecordORM(
            record_id=record.record_id,
            run_id=record.run_id,
            skill_name=record.skill_name,
            stage=record.stage,
            provider=record.provider,
            model_id=record.model_id,
            prompt_tokens=record.prompt_tokens,
            completion_tokens=record.completion_tokens,
            total_tokens=record.total_tokens,
            estimated_cost_usd=record.estimated_cost_usd,
            latency_ms=record.latency_ms,
            error=record.error,
            recorded_at=record.recorded_at,
        )

    @staticmethod
    def _from_orm(row: TokenCostRecordORM) -> TokenCostRecord:
        return TokenCostRecord(
            record_id=row.record_id,
            run_id=row.run_id,
            skill_name=row.skill_name,
            stage=row.stage,
            provider=row.provider,
            model_id=row.model_id,
            prompt_tokens=row.prompt_tokens,
            completion_tokens=row.completion_tokens,
            total_tokens=row.total_tokens,
            estimated_cost_usd=Decimal(str(row.estimated_cost_usd)),
            latency_ms=row.latency_ms,
            error=row.error,
            recorded_at=row.recorded_at,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def save(self, record: TokenCostRecord) -> None:
        """Persist a single :class:`TokenCostRecord` to the database."""
        async with self._session_factory() as session:
            session.add(self._to_orm(record))
            await session.commit()

    async def list_for_run(self, run_id: UUID) -> list[TokenCostRecord]:
        """Return all cost records for the given run."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(TokenCostRecordORM).where(TokenCostRecordORM.run_id == run_id)
            )
            rows = result.scalars().all()
            return [self._from_orm(row) for row in rows]

    async def total_cost_for_run(self, run_id: UUID) -> Decimal:
        """Return the sum of estimated_cost_usd for all records belonging to the run."""
        records = await self.list_for_run(run_id)
        return sum((r.estimated_cost_usd for r in records), Decimal("0"))
