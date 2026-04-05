from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from contracts.context_pack import SourceAuthority
from contracts.plan import BasePlan


class AssetType(StrEnum):
    METRIC = "metric"
    DASHBOARD = "dashboard"
    CHART = "chart"
    SEMANTIC_OBJECT = "semantic_object"
    DBT_MODEL = "dbt_model"


class RankedAsset(BaseModel):
    asset_type: AssetType
    name: str
    description: str | None = None
    relevance_score: float = Field(ge=0.0, le=1.0)
    url: str | None = None
    authority: SourceAuthority
    reason: str  # LLM-provided short explanation


class DiscoveryPlan(BasePlan):
    skill_name: Literal["discover_metrics_and_dashboards"] = "discover_metrics_and_dashboards"
    search_terms: list[str]  # extracted keywords
    asset_types: list[AssetType] = []  # which types to look for; empty = all
    business_domain: str | None = None
    filters: dict[str, Any] = {}


class DiscoveryResult(BaseModel):
    ranked_metrics: list[RankedAsset] = []
    ranked_dashboards: list[RankedAsset] = []
    summary: str
    total_found: int
