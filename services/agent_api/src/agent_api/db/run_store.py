import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from contracts.run import Run, RunState

from .models import RunORM


class RunStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def _orm_to_contract(self, orm: RunORM) -> Run:
        return Run(
            run_id=orm.run_id,
            user_id=orm.user_id,
            interface=orm.interface,
            request_text=orm.request_text,
            state=RunState(orm.state),
            selected_skill=orm.selected_skill,
            error_message=orm.error_message,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
            routed_at=orm.routed_at,
            planned_at=orm.planned_at,
            context_built_at=orm.context_built_at,
            validated_at=orm.validated_at,
            executing_at=orm.executing_at,
            completed_at=orm.completed_at,
        )

    async def create(self, user_id: str, interface: str, request_text: str) -> Run:
        now = datetime.now(UTC)
        run_id = uuid.uuid4()
        orm = RunORM(
            run_id=run_id,
            user_id=user_id,
            interface=interface,
            request_text=request_text,
            state=RunState.CREATED,
            created_at=now,
            updated_at=now,
        )
        async with self._session_factory() as session:
            session.add(orm)
            await session.commit()
            await session.refresh(orm)
            return self._orm_to_contract(orm)

    async def get(self, run_id: uuid.UUID) -> Run | None:
        async with self._session_factory() as session:
            result = await session.execute(select(RunORM).where(RunORM.run_id == run_id))
            orm = result.scalar_one_or_none()
            if orm is None:
                return None
            return self._orm_to_contract(orm)

    async def update_state(self, run_id: uuid.UUID, state: RunState, **kwargs) -> Run:
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            result = await session.execute(select(RunORM).where(RunORM.run_id == run_id))
            orm = result.scalar_one()
            orm.state = str(state)
            orm.updated_at = now
            # Apply optional timestamp fields and other kwargs
            _state_timestamp_map: dict[RunState, str] = {
                RunState.ROUTED: "routed_at",
                RunState.PLANNED: "planned_at",
                RunState.CONTEXT_BUILT: "context_built_at",
                RunState.VALIDATED: "validated_at",
                RunState.EXECUTING: "executing_at",
                RunState.SUCCEEDED: "completed_at",
                RunState.FAILED: "completed_at",
                RunState.CANCELLED: "completed_at",
            }
            ts_field = _state_timestamp_map.get(state)
            if ts_field:
                setattr(orm, ts_field, now)
            for key, value in kwargs.items():
                if hasattr(orm, key):
                    setattr(orm, key, value)
            await session.commit()
            await session.refresh(orm)
            return self._orm_to_contract(orm)

    async def list_for_user(self, user_id: str, limit: int = 20, offset: int = 0) -> list[Run]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(RunORM)
                .where(RunORM.user_id == user_id)
                .order_by(RunORM.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return [self._orm_to_contract(orm) for orm in result.scalars().all()]
