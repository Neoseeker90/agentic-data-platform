from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class ContentType(StrEnum):
    DBT_METRIC = "dbt_metric"
    DBT_MODEL = "dbt_model"
    LIGHTDASH_DASHBOARD = "lightdash_dashboard"
    LIGHTDASH_CHART = "lightdash_chart"
    LIGHTDASH_FIELD = "lightdash_field"


class EmbeddingRecord(BaseModel):
    content_type: ContentType
    object_ref: str
    label: str
    content_text: str
    metadata: dict = {}


class SearchResult(BaseModel):
    content_type: ContentType
    object_ref: str
    label: str
    content_text: str
    metadata: dict
    similarity: float
