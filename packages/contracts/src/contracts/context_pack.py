from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class SourceAuthority(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    SUPPORTING = "supporting"


class SourceType(StrEnum):
    LIGHTDASH_METRIC = "lightdash_metric"
    LIGHTDASH_DASHBOARD = "lightdash_dashboard"
    LIGHTDASH_CHART = "lightdash_chart"
    DBT_MODEL = "dbt_model"
    DBT_YAML = "dbt_yaml"
    DBT_METRIC = "dbt_metric"
    KPI_GLOSSARY = "kpi_glossary"
    BUSINESS_DOC = "business_doc"
    DASHBOARD_METADATA = "dashboard_metadata"


class ContextSource(BaseModel):
    source_id: UUID = Field(default_factory=uuid4)
    source_type: SourceType
    authority: SourceAuthority
    freshness: str = "unknown"  # "current" | "stale" | "unknown"
    object_ref: str  # name or id of the referenced object
    label: str
    snippet: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContextPack(BaseModel):
    pack_id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    plan_id: UUID
    skill_name: str
    sources: list[ContextSource] = Field(default_factory=list)
    unresolved_ambiguities: list[str] = Field(default_factory=list)
    token_estimate: int = 0
    artifact_key: str | None = None
    built_at: datetime = Field(default_factory=datetime.utcnow)
