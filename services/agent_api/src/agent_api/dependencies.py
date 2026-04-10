from collections.abc import AsyncGenerator
from functools import lru_cache
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.auth.stub import AuthenticatedUser, get_current_user
from agent_api.config import Settings
from agent_api.db.engine import get_db, get_session_factory
from agent_api.db.run_store import RunStore
from agent_api.db.session_store import SessionStore


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


async def get_db_session() -> AsyncGenerator[AsyncSession, Any]:
    async for session in get_db():
        yield session


def get_run_store() -> RunStore:
    return RunStore(get_session_factory())


def get_session_store() -> SessionStore:
    return SessionStore(get_session_factory())


def get_container(request: Request):
    return request.app.state.container


def get_orchestrator(request: Request):
    return request.app.state.container.orchestrator


def get_platform_router(request: Request):
    return request.app.state.container.router


def get_auditor(request: Request):
    return getattr(request.app.state.container, "auditor", None)


# Type aliases for use in route signatures
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
DBSession = Annotated[AsyncSession, Depends(get_db_session)]
