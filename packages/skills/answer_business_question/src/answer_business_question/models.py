from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from contracts.context_pack import SourceAuthority
from contracts.plan import BasePlan


class QuestionType(StrEnum):
    DEFINITION = "definition"
    COMPARISON = "comparison"
    TREND = "trend"
    NAVIGATION = "navigation"
    GENERAL = "general"


class TrustedReference(BaseModel):
    ref_type: str  # "metric" | "dashboard" | "glossary_entry" | "dbt_model"
    name: str
    url: str | None = None
    authority: SourceAuthority


class BusinessQuestionPlan(BasePlan):
    skill_name: Literal["answer_business_question"] = "answer_business_question"
    question_type: QuestionType = QuestionType.GENERAL
    identified_metrics: list[str] = []
    identified_dimensions: list[str] = []
    identified_time_range: str | None = None
    business_domain: str | None = None
    ambiguous_terms: list[str] = []
    planning_confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class BusinessQuestionResult(BaseModel):
    answer_text: str
    trusted_references: list[TrustedReference] = []
    confidence: float = Field(ge=0.0, le=1.0)
    caveat: str | None = None
    suggested_dashboards: list[str] = []
