from typing import Any, Literal

from pydantic import BaseModel


class LightdashMetric(BaseModel):
    metric_id: str
    name: str
    label: str
    description: str | None = None
    table: str
    type: str
    tags: list[str] = []
    url: str | None = None


class LightdashDimension(BaseModel):
    dimension_id: str
    name: str
    label: str
    description: str | None = None
    table: str
    type: str


class LightdashChart(BaseModel):
    chart_uuid: str
    name: str
    description: str | None = None
    space_name: str | None = None
    dashboard_uuid: str | None = None
    url: str | None = None


class LightdashDashboard(BaseModel):
    dashboard_uuid: str
    name: str
    description: str | None = None
    space_name: str | None = None
    charts: list[LightdashChart] = []
    url: str | None = None


class LightdashSearchResult(BaseModel):
    result_type: str  # "metric" | "dashboard" | "chart" | "dimension"
    name: str
    label: str
    description: str | None = None
    url: str | None = None
    object_id: str


class ExploreField(BaseModel):
    field_id: str
    label: str
    description: str | None = None
    field_type: Literal["dimension", "metric"]
    type: str = ""


class ExploreDetail(BaseModel):
    explore_name: str
    label: str
    description: str | None = None
    fields: list[ExploreField] = []


class QueryResult(BaseModel):
    rows: list[dict[str, Any]] = []
    fields: dict[str, Any] = {}
    row_count: int = 0


class LightdashSpace(BaseModel):
    space_uuid: str
    name: str
    is_private: bool = False


class SavedChartResult(BaseModel):
    chart_uuid: str
    url: str
