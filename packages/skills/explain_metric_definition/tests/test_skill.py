from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from contracts.run import Run


def _make_run() -> Run:
    return Run(
        user_id="test_user",
        interface="test",
        request_text="What does active customer mean?",
    )


def _make_prompt_loader() -> MagicMock:
    loader = MagicMock()
    loader.render.return_value = "rendered prompt"
    loader.get_version_id.return_value = "deadbeef"
    return loader


def _make_anthropic_client(plan_payload: dict, execute_payload: dict) -> MagicMock:
    plan_message = MagicMock()
    plan_message.content = [MagicMock(text=json.dumps(plan_payload))]

    execute_message = MagicMock()
    execute_message.content = [MagicMock(text=json.dumps(execute_payload))]

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(side_effect=[plan_message, execute_message])
    return client


def _make_lightdash_client_with_metric() -> MagicMock:
    metric = MagicMock()
    metric.name = "active_customer"
    metric.label = "Active Customer"
    metric.description = "Customers who purchased in the last 30 days."
    metric.table = "customers"
    metric.type = "count_distinct"
    metric.tags = []
    metric.url = "https://lightdash.example.com/metrics/active_customer"

    mock = MagicMock()
    mock.get_metric = AsyncMock(return_value=metric)
    return mock


def _make_lightdash_client_empty() -> MagicMock:
    mock = MagicMock()
    mock.get_metric = AsyncMock(return_value=None)
    return mock


def _make_lightdash_search_empty() -> MagicMock:
    mock = MagicMock()
    mock.find_relevant_context = AsyncMock(return_value=[])
    return mock


def _make_dbt_reader_empty() -> MagicMock:
    mock = MagicMock()
    mock.get_metric = MagicMock(return_value=None)
    mock.metrics_to_context_sources = MagicMock(return_value=[])
    return mock


def _make_docs_searcher_empty() -> MagicMock:
    mock = MagicMock()
    mock.search = AsyncMock(return_value=[])
    mock.to_context_sources = AsyncMock(return_value=[])
    return mock


@pytest.mark.asyncio
async def test_full_pipeline_happy_path() -> None:
    from explain_metric_definition.skill import ExplainMetricDefinitionSkill

    plan_payload = {
        "metric_name": "active customer",
        "normalized_metric_name": "active_customer",
        "related_metric_names": [],
        "business_domain": "sales",
        "intent_summary": "The user wants to understand the definition of the active customer metric.",
    }

    execute_payload = {
        "metric_name": "active_customer",
        "display_name": "Active Customer",
        "definition": "A customer who has placed at least one order in the last 30 days.",
        "business_meaning": "Active customers represent engaged buyers contributing to current revenue.",
        "caveats": ["Excludes cancelled orders."],
        "data_sources": ["dim_customers"],
        "related_dashboards": ["Customer Health Dashboard"],
        "is_definition_complete": True,
        "conflicting_definitions": [],
        "authority_level": "primary",
    }

    run = _make_run()
    client = _make_anthropic_client(plan_payload, execute_payload)
    loader = _make_prompt_loader()
    lightdash_client = _make_lightdash_client_with_metric()
    lightdash_search = _make_lightdash_search_empty()
    dbt = _make_dbt_reader_empty()
    docs = _make_docs_searcher_empty()

    skill = ExplainMetricDefinitionSkill(
        anthropic_client=client,
        prompt_loader=loader,
        lightdash_client=lightdash_client,
        lightdash_search=lightdash_search,
        dbt_reader=dbt,
        docs_searcher=docs,
    )

    # Plan
    plan = await skill.plan(run.request_text, run)
    assert plan.run_id == run.run_id
    assert plan.metric_name == "active customer"
    assert plan.normalized_metric_name == "active_customer"

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
    assert exec_result.run_id == run.run_id

    # Format
    formatted = await skill.format_result(exec_result)
    assert isinstance(formatted, str)
    assert len(formatted) > 0
    assert "Active Customer" in formatted
    assert "Definition" in formatted


@pytest.mark.asyncio
async def test_full_pipeline_metric_not_found() -> None:
    from explain_metric_definition.skill import ExplainMetricDefinitionSkill

    plan_payload = {  # type: ignore
        "metric_name": "unknown metric xyz",
        "normalized_metric_name": "unknown_metric_xyz",
        "related_metric_names": [],
        "business_domain": None,
        "intent_summary": "The user wants to understand unknown_metric_xyz.",
    }

    run = _make_run()
    # Only one LLM call needed — execution won't happen if validation fails
    plan_message = MagicMock()
    plan_message.content = [MagicMock(text=json.dumps(plan_payload))]
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=plan_message)

    loader = _make_prompt_loader()
    lightdash_client = _make_lightdash_client_empty()
    lightdash_search = _make_lightdash_search_empty()
    dbt = _make_dbt_reader_empty()
    docs = _make_docs_searcher_empty()

    skill = ExplainMetricDefinitionSkill(
        anthropic_client=client,
        prompt_loader=loader,
        lightdash_client=lightdash_client,
        lightdash_search=lightdash_search,
        dbt_reader=dbt,
        docs_searcher=docs,
    )

    # Plan
    plan = await skill.plan(run.request_text, run)

    # Build context — all adapters return empty
    context = await skill.build_context(plan, run)
    assert len(context.sources) == 0

    # Validate — should return passed=False
    validation = await skill.validate(plan, context)
    assert validation.passed is False

    # Confirm the error check is present
    error_checks = [c for c in validation.checks if not c.passed and c.severity == "error"]
    assert len(error_checks) > 0
