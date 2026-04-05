from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class RouteDecision(BaseModel):
    decision_id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    skill_name: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str | None = None
    requires_clarification: bool = False
    clarification_message: str | None = None
    candidate_skills: list[str] = Field(default_factory=list)
    prompt_version_id: str | None = None
    model_id: str | None = None
    decided_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("skill_name")
    @classmethod
    def skill_required_when_not_clarifying(
        cls, v: str | None, info: object
    ) -> str | None:
        # Validation happens at use-site; model is permissive here to allow partial states
        return v
