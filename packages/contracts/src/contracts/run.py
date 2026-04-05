from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class RunState(StrEnum):
    CREATED = "created"
    ROUTED = "routed"
    PLANNED = "planned"
    CONTEXT_BUILT = "context_built"
    VALIDATED = "validated"
    AWAITING_APPROVAL = "awaiting_approval"
    AWAITING_SKILL_CLARIFICATION = "awaiting_skill_clarification"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATES = {RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED}


class Run(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    run_id: UUID = Field(default_factory=uuid4)
    user_id: str
    interface: str
    request_text: str
    state: RunState = RunState.CREATED
    selected_skill: str | None = None
    error_message: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    routed_at: datetime | None = None
    planned_at: datetime | None = None
    context_built_at: datetime | None = None
    validated_at: datetime | None = None
    executing_at: datetime | None = None
    completed_at: datetime | None = None
