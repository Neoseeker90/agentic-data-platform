from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from contracts.context_pack import SourceAuthority
from contracts.plan import BasePlan


class ExplainMetricPlan(BasePlan):
    skill_name: Literal["explain_metric_definition"] = "explain_metric_definition"
    metric_name: str
    normalized_metric_name: str
    related_metric_names: list[str] = []
    business_domain: str | None = None


class MetricDefinitionResult(BaseModel):
    metric_name: str
    display_name: str
    definition: str
    business_meaning: str
    caveats: list[str] = []
    data_sources: list[str] = []
    related_dashboards: list[str] = []
    is_definition_complete: bool = True
    conflicting_definitions: list[str] = []
    authority_level: SourceAuthority
