from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .models import ConversationTurnORM


class SessionStore:
    MAX_HISTORY_TURNS = 10  # last 10 turns (5 exchanges)

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save_turn(
        self,
        session_id: uuid.UUID,
        role: str,
        content: str,
        run_id: uuid.UUID | None = None,
    ) -> None:
        now = datetime.now(UTC)
        orm = ConversationTurnORM(
            session_id=session_id,
            run_id=run_id,
            role=role,
            content=content,
            created_at=now,
        )
        async with self._session_factory() as session:
            session.add(orm)
            await session.commit()

    async def get_session_id_for_run(self, run_id: uuid.UUID) -> uuid.UUID | None:
        """Return the session_id of the most recent turn that references this run."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(ConversationTurnORM.session_id)
                .where(ConversationTurnORM.run_id == run_id)
                .limit(1)
            )
            return result.scalar_one_or_none()

    async def get_history(self, session_id: uuid.UUID) -> list[dict]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(ConversationTurnORM)
                .where(ConversationTurnORM.session_id == session_id)
                .order_by(ConversationTurnORM.created_at.desc())
                .limit(self.MAX_HISTORY_TURNS)
            )
            turns = result.scalars().all()
        # Reverse to chronological order (oldest first)
        return [{"role": t.role, "content": t.content} for t in reversed(turns)]
