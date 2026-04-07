import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent_api.config import Settings
from agent_api.db.engine import dispose_db_engine, init_db_engine
from agent_api.middleware.request_id import RequestIdMiddleware
from agent_api.routers import agent, feedback, health, runs, skills
from agent_api.startup import AppContainer


def _configure_logging(log_level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = Settings()
    _configure_logging(settings.log_level)
    init_db_engine(settings.database_url)
    app.state.container = AppContainer.create(settings)
    yield
    await dispose_db_engine()


app = FastAPI(
    title="Agentic Data Platform API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestIdMiddleware)

app.include_router(health.router)
app.include_router(agent.router, prefix="/agent", tags=["agent"])
app.include_router(runs.router, prefix="/runs", tags=["runs"])
app.include_router(feedback.router, prefix="/feedback", tags=["feedback"])
app.include_router(skills.router, prefix="/agent", tags=["agent"])
