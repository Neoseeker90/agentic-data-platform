from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class FeedbackFailureReason(StrEnum):
    WRONG_SKILL_SELECTED = "wrong_skill_selected"
    MISUNDERSTOOD_REQUEST = "misunderstood_request"
    MISSING_CONTEXT = "missing_context"
    WRONG_METRIC_OR_DASHBOARD = "wrong_metric_or_dashboard"
    UNCLEAR_EXPLANATION = "unclear_explanation"
    LOW_USEFULNESS = "low_usefulness"
    TOO_SLOW = "too_slow"
    OTHER = "other"


class ImplicitSignal(StrEnum):
    CLICKED_DASHBOARD = "clicked_dashboard"
    ACCEPTED_WITHOUT_RETRY = "accepted_without_retry"
    RETRIED_IMMEDIATELY = "retried_immediately"
    REFORMULATED_QUESTION = "reformulated_question"
    ABANDONED_WORKFLOW = "abandoned_workflow"
    ASKED_FOLLOWUP = "asked_followup"
    REJECTED_RESULT = "rejected_result"


class FeedbackRecord(BaseModel):
    feedback_id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    user_id: str
    helpful: bool | None = None
    score: int | None = Field(default=None, ge=1, le=5)
    comment: str | None = None
    failure_reason: FeedbackFailureReason | None = None
    implicit_signals: list[ImplicitSignal] = Field(default_factory=list)
    captured_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("score")
    @classmethod
    def validate_score(cls, v: int | None) -> int | None:
        if v is not None and not (1 <= v <= 5):
            raise ValueError("score must be between 1 and 5")
        return v
