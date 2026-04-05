from __future__ import annotations

import pytest

from contracts.context_pack import ContextPack, ContextSource, SourceAuthority, SourceType
from contracts.run import Run
from explain_metric_definition.models import ExplainMetricPlan


def _make_run() -> Run:
    return Run(
        user_id="test_user",
        interface="test",
        request_text="What does active customer mean?",
    )


def _make_plan(run: Run) -> ExplainMetricPlan:
    return ExplainMetricPlan(
        run_id=run.run_id,
        intent_summary="Test intent",
        metric_name="active customer",
        normalized_metric_name="active_customer",
    )


def _make_context_pack(
    plan: ExplainMetricPlan,
    sources: list[ContextSource] | None = None,
) -> ContextPack:
    return ContextPack(
        run_id=plan.run_id,
        plan_id=plan.plan_id,
        skill_name="explain_metric_definition",
        sources=sources or [],
    )


def _make_primary_source() -> ContextSource:
    return ContextSource(
        source_type=SourceType.LIGHTDASH_METRIC,
        authority=SourceAuthority.PRIMARY,
        freshness="current",
        object_ref="active_customer",
        label="Active Customer",
        snippet="A customer who placed an order in the last 30 days.",
    )


def _make_secondary_source() -> ContextSource:
    return ContextSource(
        source_type=SourceType.KPI_GLOSSARY,
        authority=SourceAuthority.SECONDARY,
        freshness="current",
        object_ref="glossary_active_customer",
        label="Active Customer Glossary",
        snippet="Glossary definition of active customer.",
    )


@pytest.mark.asyncio
async def test_hard_fails_when_no_sources() -> None:
    from explain_metric_definition.validator import ExplainMetricValidator

    run = _make_run()
    plan = _make_plan(run)
    context = _make_context_pack(plan, sources=[])

    validator = ExplainMetricValidator()
    result = await validator.validate(plan, context)

    assert result.passed is False
    metric_check = next(c for c in result.checks if c.check_name == "metric_found")
    assert metric_check.passed is False
    assert metric_check.severity == "error"
    assert "active_customer" in metric_check.message


@pytest.mark.asyncio
async def test_passes_with_any_source() -> None:
    from explain_metric_definition.validator import ExplainMetricValidator

    run = _make_run()
    plan = _make_plan(run)
    context = _make_context_pack(plan, sources=[_make_primary_source()])

    validator = ExplainMetricValidator()
    result = await validator.validate(plan, context)

    assert result.passed is True
    metric_check = next(c for c in result.checks if c.check_name == "metric_found")
    assert metric_check.passed is True


@pytest.mark.asyncio
async def test_warns_when_no_primary() -> None:
    from explain_metric_definition.validator import ExplainMetricValidator

    run = _make_run()
    plan = _make_plan(run)
    # Only secondary source — no primary
    context = _make_context_pack(plan, sources=[_make_secondary_source()])

    validator = ExplainMetricValidator()
    result = await validator.validate(plan, context)

    # Overall still passes (no error-level failure) because metric_found passes (sources > 0)
    assert result.passed is True

    primary_check = next(c for c in result.checks if c.check_name == "has_primary_definition")
    assert primary_check.passed is False
    assert primary_check.severity == "warning"


@pytest.mark.asyncio
async def test_requires_approval_is_false() -> None:
    from explain_metric_definition.validator import ExplainMetricValidator

    run = _make_run()
    plan = _make_plan(run)
    context = _make_context_pack(plan, sources=[_make_primary_source()])

    validator = ExplainMetricValidator()
    result = await validator.validate(plan, context)

    assert result.requires_approval is False
    assert result.risk_level == "low"
