from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ArtifactRef(BaseModel):
    artifact_key: str
    artifact_type: str
    label: str


class ExecutionResult(BaseModel):
    result_id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    plan_id: UUID
    success: bool
    output: dict[str, Any] = Field(default_factory=dict)
    formatted_response: str | None = None
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    llm_call_ids: list[UUID] = Field(default_factory=list)
    executed_at: datetime = Field(default_factory=datetime.utcnow)
