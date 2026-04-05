from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from contracts.context_pack import ContextSource, SourceAuthority, SourceType
from contracts.run import Run

from answer_business_question.models import BusinessQuestionPlan


def _make_run(request_text: str = "What is our churn rate?") -> Run:
    return Run(
        user_id="test_user",
        interface="test",
        request_text=request_text,
    )


def _make_plan(
    run: Run,
    metrics: list[str] | None = None,
    dimensions: list[str] | None = None,
    ambiguous: list[str] | None = None,
) -> BusinessQuestionPlan:
    return BusinessQuestionPlan(
        run_id=run.run_id,
        intent_summary="Test intent",
        identified_metrics=metrics or [],
        identified_dimensions=dimensions or [],
        ambiguous_terms=ambiguous or [],
    )


def _make_context_source(object_ref: str, authority: SourceAuthority = SourceAuthority.PRIMARY) -> ContextSource:
    return ContextSource(
        source_type=SourceType.LIGHTDASH_METRIC,
        authority=authority,
        freshness="current",
        object_ref=object_ref,
        label=object_ref,
        snippet=f"Snippet for {object_ref}",
    )


@pytest.mark.asyncio
async def test_builds_context_from_all_sources() -> None:
    from answer_business_question.context_builder import BusinessQuestionContextBuilder

    lightdash_source = _make_context_source("churn_rate_ld")
    dbt_source = _make_context_source("churn_rate_dbt")
    docs_source = _make_context_source("doc_churn_glossary", SourceAuthority.SECONDARY)

    lightdash_mock = MagicMock()
    lightdash_mock.find_relevant_context = AsyncMock(return_value=[lightdash_source])

    dbt_metric = MagicMock()
    dbt_metric.name = "churn_rate"
    dbt_mock = MagicMock()
    dbt_mock.search_metrics = MagicMock(return_value=[dbt_metric])
    dbt_mock.metrics_to_context_sources = MagicMock(return_value=[dbt_source])

    docs_mock = MagicMock()
    docs_mock.search = AsyncMock(return_value=[])
    docs_mock.to_context_sources = AsyncMock(return_value=[docs_source])

    run = _make_run()
    plan = _make_plan(run, metrics=["churn_rate"])

    builder = BusinessQuestionContextBuilder(lightdash_mock, dbt_mock, docs_mock)
    pack = await builder.build_context(plan, run)

    object_refs = {s.object_ref for s in pack.sources}
    assert "churn_rate_ld" in object_refs
    assert "churn_rate_dbt" in object_refs
    # docs_source appears from both KPI_GLOSSARY and BUSINESS_LOGIC calls; deduplicated to one
    assert "doc_churn_glossary" in object_refs
    assert len(pack.sources) >= 3


@pytest.mark.asyncio
async def test_deduplicates_by_object_ref() -> None:
    from answer_business_question.context_builder import BusinessQuestionContextBuilder

    # Both lightdash and dbt return a source with the same object_ref
    duplicate_source_a = _make_context_source("net_revenue")
    duplicate_source_b = _make_context_source("net_revenue")  # same ref

    lightdash_mock = MagicMock()
    lightdash_mock.find_relevant_context = AsyncMock(return_value=[duplicate_source_a])

    dbt_mock = MagicMock()
    dbt_mock.search_metrics = MagicMock(return_value=[])
    dbt_mock.metrics_to_context_sources = MagicMock(return_value=[duplicate_source_b])

    docs_mock = MagicMock()
    docs_mock.search = AsyncMock(return_value=[])
    docs_mock.to_context_sources = AsyncMock(return_value=[])

    run = _make_run("What is net revenue?")
    plan = _make_plan(run, metrics=["net_revenue"])

    builder = BusinessQuestionContextBuilder(lightdash_mock, dbt_mock, docs_mock)
    pack = await builder.build_context(plan, run)

    refs = [s.object_ref for s in pack.sources]
    assert refs.count("net_revenue") == 1


@pytest.mark.asyncio
async def test_unresolved_ambiguities_populated() -> None:
    from answer_business_question.context_builder import BusinessQuestionContextBuilder

    lightdash_mock = MagicMock()
    lightdash_mock.find_relevant_context = AsyncMock(return_value=[])

    dbt_mock = MagicMock()
    dbt_mock.search_metrics = MagicMock(return_value=[])
    dbt_mock.metrics_to_context_sources = MagicMock(return_value=[])

    docs_mock = MagicMock()
    docs_mock.search = AsyncMock(return_value=[])
    docs_mock.to_context_sources = AsyncMock(return_value=[])

    run = _make_run("What does 'active customer' mean?")
    plan = _make_plan(run, ambiguous=["active customer"])

    builder = BusinessQuestionContextBuilder(lightdash_mock, dbt_mock, docs_mock)
    pack = await builder.build_context(plan, run)

    assert "active customer" in pack.unresolved_ambiguities
