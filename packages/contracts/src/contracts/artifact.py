from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Artifact(BaseModel):
    artifact_id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    artifact_key: str  # S3 object key
    artifact_type: str  # "run_bundle" | "context_pack" | "response" | "report"
    label: str
    size_bytes: int | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
