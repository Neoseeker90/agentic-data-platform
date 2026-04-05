from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ValidationCheck(BaseModel):
    check_name: str
    passed: bool
    message: str | None = None
    severity: str = "error"  # "error" | "warning"


class ValidationResult(BaseModel):
    result_id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    plan_id: UUID
    passed: bool
    checks: list[ValidationCheck] = Field(default_factory=list)
    risk_level: str = "low"  # "low" | "medium" | "high"
    requires_approval: bool = False
    validated_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def errors(self) -> list[ValidationCheck]:
        return [c for c in self.checks if not c.passed and c.severity == "error"]

    @property
    def warnings(self) -> list[ValidationCheck]:
        return [c for c in self.checks if not c.passed and c.severity == "warning"]
