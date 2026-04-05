from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field

from contracts.feedback import FeedbackFailureReason, ImplicitSignal


class AskRequest(BaseModel):
    request_text: str = Field(min_length=1, max_length=4096)
    interface: str = "api"
    context: dict | None = None
    session_id: uuid.UUID | None = None


class ClarificationRequest(BaseModel):
    response: str


class ApprovalRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    comment: str | None = None


class ExplicitFeedbackRequest(BaseModel):
    helpful: bool | None = None
    score: int | None = Field(None, ge=1, le=5)
    comment: str | None = None
    failure_reason: FeedbackFailureReason | None = None


class ImplicitSignalRequest(BaseModel):
    signal: ImplicitSignal
