from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class DocType(StrEnum):
    KPI_GLOSSARY = "kpi_glossary"
    BUSINESS_LOGIC = "business_logic"
    CAVEAT = "caveat"


class BusinessDoc(BaseModel):
    doc_id: UUID = Field(default_factory=uuid4)
    doc_type: DocType
    title: str
    content: str
    owner: str | None = None
    source_path: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BusinessDocResult(BaseModel):
    doc: BusinessDoc
    relevance_rank: int
    snippet: str
