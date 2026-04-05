from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from contracts.feedback import FeedbackFailureReason


class EvaluationCase(BaseModel):
    case_id: UUID = Field(default_factory=uuid4)
    source_run_id: UUID | None = None
    request_text: str
    expected_skill: str | None = None
    expected_asset_refs: list[str] = Field(default_factory=list)
    observed_skill: str | None = None
    observed_response: str | None = None
    feedback_score: int | None = None
    feedback_failure_reason: FeedbackFailureReason | None = None
    human_label: str | None = None  # "correct" | "wrong_skill" | "incomplete" | "hallucination"
    dataset_tags: list[str] = Field(default_factory=list)
    status: str = "pending"  # "pending" | "passing" | "failing"
    created_by: str = "auto"  # "auto" | "human"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
