from __future__ import annotations

import pytest

from answer_business_question.models import BusinessQuestionPlan
from contracts.context_pack import ContextPack, ContextSource, SourceAuthority, SourceType
from contracts.run import Run


def _make_run() -> Run:
    return Run(
        user_id="test_user",
        interface="test",
        request_text="What is our churn rate?",
    )


def _make_plan(
    run: Run,
    metrics: list[str] | None = None,
    confidence: float = 0.9,
    ambiguous: list[str] | None = None,
) -> BusinessQuestionPlan:
    return BusinessQuestionPlan(
        run_id=run.run_id,
        intent_summary="Test intent",
        identified_metrics=metrics or [],
        planning_confidence=confidence,
        ambiguous_terms=ambiguous or [],
    )


def _make_context_pack(
    plan: BusinessQuestionPlan,
    sources: list[ContextSource] | None = None,
    unresolved: list[str] | None = None,
) -> ContextPack:
    return ContextPack(
        run_id=plan.run_id,
        plan_id=plan.plan_id,
        skill_name="answer_business_question",
        sources=sources or [],
        unresolved_ambiguities=unresolved or [],
    )


def _make_primary_source() -> ContextSource:
    return ContextSource(
        source_type=SourceType.LIGHTDASH_METRIC,
        authority=SourceAuthority.PRIMARY,
        freshness="current",
        object_ref="churn_rate",
        label="Churn Rate",
        snippet="Monthly churn rate metric.",
    )


@pytest.mark.asyncio
async def test_passes_when_primary_source_present() -> None:
    from answer_business_question.validator import BusinessQuestionValidator

    run = _make_run()
    plan = _make_plan(run, metrics=["churn_rate"])
    context = _make_context_pack(plan, sources=[_make_primary_source()])

    validator = BusinessQuestionValidator()
    result = await validator.validate(plan, context)

    assert result.passed is True
    auth_check = next(c for c in result.checks if c.check_name == "has_authoritative_source")
    assert auth_check.passed is True


@pytest.mark.asyncio
async def test_fails_when_no_source_and_metrics_identified() -> None:
    from answer_business_question.validator import BusinessQuestionValidator

    run = _make_run()
    plan = _make_plan(run, metrics=["churn_rate"])
    context = _make_context_pack(plan, sources=[])

    validator = BusinessQuestionValidator()
    result = await validator.validate(plan, context)

    assert result.passed is False
    auth_check = next(c for c in result.checks if c.check_name == "has_authoritative_source")
    assert auth_check.passed is False
    assert auth_check.severity == "error"


@pytest.mark.asyncio
async def test_warns_on_low_confidence() -> None:
    from answer_business_question.validator import BusinessQuestionValidator

    run = _make_run()
    plan = _make_plan(run, confidence=0.3)
    context = _make_context_pack(plan, sources=[_make_primary_source()])

    validator = BusinessQuestionValidator()
    result = await validator.validate(plan, context)

    confidence_check = next(c for c in result.checks if c.check_name == "low_planning_confidence")
    assert confidence_check.passed is False
    assert confidence_check.severity == "warning"
    # Still passes overall since no error-level failures
    assert result.passed is True


@pytest.mark.asyncio
async def test_requires_approval_is_false() -> None:
    from answer_business_question.validator import BusinessQuestionValidator

    run = _make_run()
    plan = _make_plan(run)
    context = _make_context_pack(plan)

    validator = BusinessQuestionValidator()
    result = await validator.validate(plan, context)

    assert result.requires_approval is False
