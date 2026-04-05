from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from agent_api.config import Settings
from agent_api.dependencies import get_settings

router = APIRouter()


@router.get("/health")
async def health_check(
    settings: Annotated[Settings, Depends(get_settings)],
) -> JSONResponse:
    return JSONResponse({"status": "ok", "environment": settings.environment})
