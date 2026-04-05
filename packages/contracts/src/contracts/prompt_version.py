from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class PromptVersion(BaseModel):
    version_id: UUID = Field(default_factory=uuid4)
    component: str  # e.g. "router", "skill.answer_business_question.planner"
    version_hash: str  # SHA-256 of content
    content: str
    model_id: str
    is_active: bool = False
    deployed_at: datetime | None = None
    created_by: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
