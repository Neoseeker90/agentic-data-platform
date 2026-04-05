from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class DbtNodeType(StrEnum):
    MODEL = "model"
    SOURCE = "source"
    SEED = "seed"
    EXPOSURE = "exposure"
    METRIC = "metric"


class DbtColumn(BaseModel):
    name: str
    description: str | None = None
    data_type: str | None = None


class DbtModel(BaseModel):
    unique_id: str
    name: str
    description: str | None = None
    schema_name: str | None = None
    tags: list[str] = []
    columns: dict[str, DbtColumn] = {}
    raw_sql: str | None = None
    depends_on: list[str] = []


class DbtMetric(BaseModel):
    unique_id: str
    name: str
    label: str | None = None
    description: str | None = None
    type: str
    expression: str | None = None
    depends_on: list[str] = []


class DbtExposure(BaseModel):
    unique_id: str
    name: str
    description: str | None = None
    type: str
    depends_on: list[str] = []
    url: str | None = None


class DbtSource(BaseModel):
    unique_id: str
    name: str
    schema_name: str | None = None
    description: str | None = None
    tables: list[str] = []
