import uuid
from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

TIMESTAMPTZ = TIMESTAMP(timezone=True)


class Base(DeclarativeBase):
    pass


class RunORM(Base):
    __tablename__ = "runs"

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    interface: Mapped[str] = mapped_column(Text, nullable=False)
    request_text: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    selected_skill: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=func.now()
    )
    routed_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    planned_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    context_built_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    executing_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)


class RouteDecisionORM(Base):
    __tablename__ = "route_decisions"

    decision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.run_id"), nullable=False
    )
    skill_name: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    requires_clarification: Mapped[bool] = mapped_column(Boolean, nullable=False)
    clarification_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    candidate_skills: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    prompt_version_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=func.now()
    )


class PlanORM(Base):
    __tablename__ = "plans"

    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.run_id"), nullable=False
    )
    skill_name: Mapped[str] = mapped_column(Text, nullable=False)
    intent_summary: Mapped[str] = mapped_column(Text, nullable=False)
    extracted_entities: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    prompt_version_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    planned_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=func.now()
    )


class ContextPackORM(Base):
    __tablename__ = "context_packs"

    pack_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.run_id"), nullable=False
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.plan_id"), nullable=False
    )
    skill_name: Mapped[str] = mapped_column(Text, nullable=False)
    sources: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    unresolved_ambiguities: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    token_estimate: Mapped[int] = mapped_column(Integer, nullable=False)
    artifact_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    built_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=func.now()
    )


class ValidationResultORM(Base):
    __tablename__ = "validation_results"

    result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.run_id"), nullable=False
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.plan_id"), nullable=False
    )
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    checks: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    risk_level: Mapped[str] = mapped_column(Text, nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False)
    validated_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=func.now()
    )


class ExecutionResultORM(Base):
    __tablename__ = "execution_results"

    result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.run_id"), nullable=False
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.plan_id"), nullable=False
    )
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    output: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    formatted_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifacts: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    llm_call_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    executed_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=func.now()
    )


class FeedbackORM(Base):
    __tablename__ = "feedback"

    feedback_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.run_id"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    helpful: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    implicit_signals: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    captured_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=func.now()
    )


class TokenCostRecordORM(Base):
    __tablename__ = "token_cost_records"

    record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.run_id"), nullable=True
    )
    skill_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    stage: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model_id: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_cost_usd: Mapped[float] = mapped_column(Numeric, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=func.now()
    )


class EvaluationCaseORM(Base):
    __tablename__ = "evaluation_cases"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    request_text: Mapped[str] = mapped_column(Text, nullable=False)
    expected_skill: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_asset_refs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    observed_skill: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    feedback_failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    human_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    dataset_tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=func.now()
    )


class PromptVersionORM(Base):
    __tablename__ = "prompt_versions"

    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    component: Mapped[str] = mapped_column(Text, nullable=False)
    version_hash: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model_id: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    deployed_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    created_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=func.now()
    )


class ConversationTurnORM(Base):
    __tablename__ = "conversation_turns"

    turn_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.run_id"), nullable=True
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=func.now()
    )
