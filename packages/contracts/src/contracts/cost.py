from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class TokenCostRecord(BaseModel):
    record_id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    skill_name: str | None = None
    stage: str  # "routing" | "planning" | "execution" | "formatting"
    provider: str
    model_id: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: Decimal
    latency_ms: int
    error: str | None = None
    recorded_at: datetime = Field(default_factory=datetime.utcnow)
