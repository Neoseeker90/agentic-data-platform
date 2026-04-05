from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class BasePlan(BaseModel):
    plan_id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    skill_name: str
    intent_summary: str
    extracted_entities: dict[str, Any] = Field(default_factory=dict)
    prompt_version_id: str | None = None
    model_id: str | None = None
    planned_at: datetime = Field(default_factory=datetime.utcnow)
