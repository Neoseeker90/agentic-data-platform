"""PromptVersionRegistry — register and query prompt versions."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.db.models import PromptVersionORM
from contracts.prompt_version import PromptVersion

logger = logging.getLogger(__name__)


class PromptVersionRegistry:
    """Tracks prompt versions by content hash.

    A new row is only inserted when the (component, version_hash) pair does
    not yet exist, making registration idempotent.
    """

    def __init__(self, session_factory: Callable[..., AsyncSession]) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _compute_hash(content: str) -> str:
        """Return the SHA-256 hex digest of *content*."""
        return hashlib.sha256(content.encode()).hexdigest()

    async def register_if_new(
        self,
        component: str,
        content: str,
        model_id: str,
        created_by: str | None = None,
    ) -> str:
        """Register a prompt version if no matching (component, hash) row exists.

        Returns the SHA-256 version hash (64-char hex string) in all cases.
        """
        version_hash = self._compute_hash(content)

        async with self._session_factory() as session:
            existing = await session.execute(
                select(PromptVersionORM).where(
                    PromptVersionORM.component == component,
                    PromptVersionORM.version_hash == version_hash,
                )
            )
            row = existing.scalar_one_or_none()

            if row is None:
                session.add(
                    PromptVersionORM(
                        version_id=uuid4(),
                        component=component,
                        version_hash=version_hash,
                        content=content,
                        model_id=model_id,
                        is_active=False,
                        deployed_at=None,
                        created_by=created_by,
                        created_at=datetime.now(UTC),
                    )
                )
                await session.commit()
                logger.debug(
                    "Registered new prompt version component=%s hash=%s",
                    component,
                    version_hash,
                )
            else:
                logger.debug(
                    "Prompt version already exists component=%s hash=%s",
                    component,
                    version_hash,
                )

        return version_hash

    async def get_active_prompt(self, component: str) -> PromptVersion | None:
        """Return the active :class:`~contracts.prompt_version.PromptVersion` for *component*,
        or ``None`` if none is active.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(PromptVersionORM).where(
                    PromptVersionORM.component == component,
                    PromptVersionORM.is_active.is_(True),
                )
            )
            row = result.scalar_one_or_none()

        if row is None:
            return None

        return PromptVersion(
            version_id=row.version_id,
            component=row.component,
            version_hash=row.version_hash,
            content=row.content,
            model_id=row.model_id,
            is_active=row.is_active,
            deployed_at=row.deployed_at,
            created_by=row.created_by,
            created_at=row.created_at,
        )
