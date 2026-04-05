from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class AskResponse(BaseModel):
    run_id: uuid.UUID
    state: str
    session_id: uuid.UUID | None = None


class RunStatusResponse(BaseModel):
    run_id: uuid.UUID
    state: str
    selected_skill: str | None
    created_at: datetime
    updated_at: datetime
    clarification_required: bool = False
    clarification_question: str | None = None
    error_message: str | None = None
    response: str | None = None  # populated when state=succeeded


class FeedbackResponse(BaseModel):
    feedback_id: uuid.UUID
    run_id: uuid.UUID


class SkillInfo(BaseModel):
    name: str
    description: str
    risk_level: str


class SkillListResponse(BaseModel):
    skills: list[SkillInfo]
