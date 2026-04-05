from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from contracts.plan import BasePlan


class DataQueryPlan(BasePlan):
    skill_name: Literal["execute_data_question"] = "execute_data_question"
    explore_name: str = ""
    dimensions: list[str] = []
    metrics: list[str] = []
    filters: dict = {}
    sorts: list[dict] = []
    limit: int = 100
    answer_type: Literal["chart", "single_value", "table"] = "table"
    chart_title: str = ""
    intent_summary: str = ""
    planning_confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class DataQueryResult(BaseModel):
    answer_text: str = ""
    rows: list[dict[str, Any]] = []
    row_count: int = 0
    chart_url: str | None = None
    chart_uuid: str | None = None
    answer_type: str = "table"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    # Query metadata for display
    explore_name: str = ""
    dimensions: list[str] = []
    metrics: list[str] = []
    fields_metadata: dict[str, Any] = {}  # field_id -> {label, field_type}
