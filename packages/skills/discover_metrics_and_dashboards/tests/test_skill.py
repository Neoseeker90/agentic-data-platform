from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from contracts.context_pack import ContextSource, SourceAuthority, SourceType
from contracts.run import Run


def _make_run() -> Run:
    return Run(
        user_id="test_user",
        interface="test",
        request_text="Which dashboard for weekly Germany sales?",
    )


def _make_prompt_loader() -> MagicMock:
    loader = MagicMock()
    loader.render.return_value = "rendered prompt"
    loader.get_version_id.return_value = "deadbeef"
    return loader


def _make_anthropic_client(plan_payload: dict, rank_payload: list) -> MagicMock:
    plan_message = MagicMock()
    plan_message.content = [MagicMock(text=json.dumps(plan_payload))]

    rank_message = MagicMock()
    rank_message.content = [MagicMock(text=json.dumps(rank_payload))]

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(side_effect=[plan_message, rank_message])
    return client


def _make_anthropic_client_plan_only(plan_payload: dict) -> MagicMock:
    plan_message = MagicMock()
    plan_message.content = [MagicMock(text=json.dumps(plan_payload))]

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=plan_message)
    return client


def _make_lightdash_search_with_dashboard() -> MagicMock:
    source = ContextSource(
        source_type=SourceType.LIGHTDASH_DASHBOARD,
        authority=SourceAuthority.SECONDARY,
        freshness="current",
        object_ref="germany_weekly_sales_dashboard",
        label="Germany Weekly Sales",
        snippet="Weekly sales breakdown for the Germany market.",
        metadata={"url": "https://lightdash.example.com/dashboards/de-weekly"},
    )
    mock = MagicMock()
    mock.find_relevant_context = AsyncMock(return_value=[source])
    return mock


def _make_lightdash_search_empty() -> MagicMock:
    mock = MagicMock()
    mock.find_relevant_context = AsyncMock(return_value=[])
    return mock


def _make_dbt_reader() -> MagicMock:
    mock = MagicMock()
    mock.search_models = MagicMock(return_value=[])
    mock.search_metrics = MagicMock(return_value=[])
    mock.to_context_sources = MagicMock(return_value=[])
    mock.metrics_to_context_sources = MagicMock(return_value=[])
    return mock


def _make_docs_searcher() -> MagicMock:
    mock = MagicMock()
    mock.search = AsyncMock(return_value=[])
    mock.to_context_sources = AsyncMock(return_value=[])
    return mock


@pytest.mark.asyncio
async def test_full_pipeline_happy_path() -> None:
    from discover_metrics_and_dashboards.skill import DiscoverMetricsAndDashboardsSkill

    plan_payload = {
        "search_terms": ["weekly sales", "germany"],
        "asset_types": ["dashboard"],
        "business_domain": "sales",
        "intent_summary": "The user wants to find a dashboard showing weekly Germany sales.",
    }

    rank_payload = [
        {
            "name": "germany_weekly_sales_dashboard",
            "relevance_score": 1.0,
            "reason": "Directly matches the Germany weekly sales dashboard request.",
        }
    ]

    run = _make_run()
    client = _make_anthropic_client(plan_payload, rank_payload)
    loader = _make_prompt_loader()
    lightdash = _make_lightdash_search_with_dashboard()
    dbt = _make_dbt_reader()
    docs = _make_docs_searcher()

    skill = DiscoverMetricsAndDashboardsSkill(
        anthropic_client=client,
        prompt_loader=loader,
        lightdash_search=lightdash,
        dbt_reader=dbt,
        docs_searcher=docs,
    )

    # Plan
    plan = await skill.plan(run.request_text, run)
    assert plan.run_id == run.run_id
    assert "weekly sales" in plan.search_terms

    # Build context
    context = await skill.build_context(plan, run)
    assert len(context.sources) > 0

    # Validate
    validation = await skill.validate(plan, context)
    assert validation.passed is True
    assert validation.requires_approval is False

    # Execute
    exec_result = await skill.execute(plan, context)
    assert exec_result.success is True

    # Format
    formatted = await skill.format_result(exec_result)
    assert isinstance(formatted, str)
    assert len(formatted) > 0


@pytest.mark.asyncio
async def test_full_pipeline_no_results() -> None:
    from discover_metrics_and_dashboards.skill import DiscoverMetricsAndDashboardsSkill

    plan_payload = {
        "search_terms": ["obscure_metric_xyz"],
        "asset_types": [],
        "business_domain": None,
        "intent_summary": "The user wants to find an obscure metric.",
    }

    run = _make_run()
    # Only one LLM call happens (for planning); executor returns empty without calling LLM
    client = _make_anthropic_client_plan_only(plan_payload)
    loader = _make_prompt_loader()
    lightdash = _make_lightdash_search_empty()
    dbt = _make_dbt_reader()
    docs = _make_docs_searcher()

    skill = DiscoverMetricsAndDashboardsSkill(
        anthropic_client=client,
        prompt_loader=loader,
        lightdash_search=lightdash,
        dbt_reader=dbt,
        docs_searcher=docs,
    )

    plan = await skill.plan(run.request_text, run)
    context = await skill.build_context(plan, run)
    assert len(context.sources) == 0

    validation = await skill.validate(plan, context)
    assert validation.passed is True  # always passes

    exec_result = await skill.execute(plan, context)
    assert exec_result.success is True
    assert exec_result.output["total_found"] == 0

    formatted = await skill.format_result(exec_result)
    assert "No matching assets" in formatted
