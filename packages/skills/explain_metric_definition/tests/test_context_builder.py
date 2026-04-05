from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from contracts.context_pack import ContextSource, SourceAuthority, SourceType
from contracts.run import Run

from explain_metric_definition.models import ExplainMetricPlan


def _make_run() -> Run:
    return Run(
        user_id="test_user",
        interface="test",
        request_text="What does active customer mean?",
    )


def _make_plan(run: Run, metric_name: str = "active customer") -> ExplainMetricPlan:
    normalized = metric_name.lower().replace(" ", "_")
    return ExplainMetricPlan(
        run_id=run.run_id,
        intent_summary="Test intent",
        metric_name=metric_name,
        normalized_metric_name=normalized,
    )


def _make_context_source(
    object_ref: str,
    authority: SourceAuthority = SourceAuthority.PRIMARY,
    source_type: SourceType = SourceType.LIGHTDASH_METRIC,
) -> ContextSource:
    return ContextSource(
        source_type=source_type,
        authority=authority,
        freshness="current",
        object_ref=object_ref,
        label=object_ref,
        snippet=f"Snippet for {object_ref}",
    )


@pytest.mark.asyncio
async def test_builds_context_when_metric_found_in_lightdash() -> None:
    from explain_metric_definition.context_builder import ExplainMetricContextBuilder

    lightdash_metric = MagicMock()
    lightdash_metric.name = "active_customer"
    lightdash_metric.label = "Active Customer"
    lightdash_metric.description = "A customer who made a purchase in the last 30 days."
    lightdash_metric.table = "customers"
    lightdash_metric.type = "count_distinct"
    lightdash_metric.tags = []
    lightdash_metric.url = None

    lightdash_client_mock = MagicMock()
    lightdash_client_mock.get_metric = AsyncMock(return_value=lightdash_metric)

    lightdash_search_mock = MagicMock()
    lightdash_search_mock.find_relevant_context = AsyncMock(return_value=[])

    dbt_mock = MagicMock()
    dbt_mock.get_metric = MagicMock(return_value=None)
    dbt_mock.metrics_to_context_sources = MagicMock(return_value=[])

    docs_mock = MagicMock()
    docs_mock.search = AsyncMock(return_value=[])
    docs_mock.to_context_sources = AsyncMock(return_value=[])

    run = _make_run()
    plan = _make_plan(run)

    builder = ExplainMetricContextBuilder(
        lightdash_client_mock, lightdash_search_mock, dbt_mock, docs_mock
    )
    pack = await builder.build_context(plan, run)

    assert len(pack.sources) > 0
    primary_sources = [s for s in pack.sources if s.authority == SourceAuthority.PRIMARY]
    assert len(primary_sources) > 0
    assert primary_sources[0].object_ref == "active_customer"
    assert pack.unresolved_ambiguities == []


@pytest.mark.asyncio
async def test_unresolved_ambiguity_when_metric_not_found() -> None:
    from explain_metric_definition.context_builder import ExplainMetricContextBuilder

    lightdash_client_mock = MagicMock()
    lightdash_client_mock.get_metric = AsyncMock(return_value=None)

    lightdash_search_mock = MagicMock()
    lightdash_search_mock.find_relevant_context = AsyncMock(return_value=[])

    dbt_mock = MagicMock()
    dbt_mock.get_metric = MagicMock(return_value=None)
    dbt_mock.metrics_to_context_sources = MagicMock(return_value=[])

    docs_mock = MagicMock()
    docs_mock.search = AsyncMock(return_value=[])
    docs_mock.to_context_sources = AsyncMock(return_value=[])

    run = _make_run()
    plan = _make_plan(run, metric_name="unknown_metric_xyz")

    builder = ExplainMetricContextBuilder(
        lightdash_client_mock, lightdash_search_mock, dbt_mock, docs_mock
    )
    pack = await builder.build_context(plan, run)

    assert len(pack.sources) == 0
    assert len(pack.unresolved_ambiguities) > 0
    assert "unknown_metric_xyz" in pack.unresolved_ambiguities[0]


@pytest.mark.asyncio
async def test_context_includes_glossary_results() -> None:
    from explain_metric_definition.context_builder import ExplainMetricContextBuilder

    glossary_source = _make_context_source(
        "glossary_active_customer",
        authority=SourceAuthority.SECONDARY,
        source_type=SourceType.KPI_GLOSSARY,
    )

    lightdash_client_mock = MagicMock()
    lightdash_client_mock.get_metric = AsyncMock(return_value=None)

    lightdash_search_mock = MagicMock()
    lightdash_search_mock.find_relevant_context = AsyncMock(return_value=[])

    dbt_mock = MagicMock()
    dbt_mock.get_metric = MagicMock(return_value=None)
    dbt_mock.metrics_to_context_sources = MagicMock(return_value=[])

    docs_mock = MagicMock()
    docs_mock.search = AsyncMock(return_value=["raw_doc_result"])
    docs_mock.to_context_sources = AsyncMock(return_value=[glossary_source])

    run = _make_run()
    plan = _make_plan(run)

    builder = ExplainMetricContextBuilder(
        lightdash_client_mock, lightdash_search_mock, dbt_mock, docs_mock
    )
    pack = await builder.build_context(plan, run)

    object_refs = {s.object_ref for s in pack.sources}
    assert "glossary_active_customer" in object_refs
    glossary_source_found = next(
        s for s in pack.sources if s.object_ref == "glossary_active_customer"
    )
    assert glossary_source_found.source_type == SourceType.KPI_GLOSSARY
