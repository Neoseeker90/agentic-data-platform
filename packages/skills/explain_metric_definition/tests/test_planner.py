from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from contracts.run import Run
from skill_sdk.exceptions import PlanningError


def _make_prompt_loader() -> MagicMock:
    loader = MagicMock()
    loader.render.return_value = "rendered prompt"
    loader.get_version_id.return_value = "abc123"
    return loader


def _make_anthropic_client(response_text: str) -> MagicMock:
    message_mock = MagicMock()
    message_mock.content = [MagicMock(text=response_text)]

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=message_mock)
    return client


def _make_run() -> Run:
    return Run(
        user_id="test_user",
        interface="test",
        request_text="What does active customer mean?",
    )


@pytest.mark.asyncio
async def test_plan_extracts_metric_name() -> None:
    from explain_metric_definition.planner import ExplainMetricPlanner

    response_payload = {
        "metric_name": "active customer",
        "normalized_metric_name": "active_customer",
        "related_metric_names": [],
        "business_domain": "sales",
        "intent_summary": "The user wants to understand the definition of the active customer metric.",
    }

    client = _make_anthropic_client(json.dumps(response_payload))
    loader = _make_prompt_loader()
    run = _make_run()

    planner = ExplainMetricPlanner(client, loader)
    plan = await planner.plan(run.request_text, run)

    assert plan.metric_name == "active customer"
    assert plan.normalized_metric_name == "active_customer"
    assert plan.run_id == run.run_id


@pytest.mark.asyncio
async def test_plan_normalizes_name() -> None:
    from explain_metric_definition.planner import ExplainMetricPlanner

    response_payload = {
        "metric_name": "Gross Merchandise Value",
        "normalized_metric_name": "gross_merchandise_value",
        "related_metric_names": ["net_revenue"],
        "business_domain": "finance",
        "intent_summary": "The user wants to understand Gross Merchandise Value.",
    }

    client = _make_anthropic_client(json.dumps(response_payload))
    loader = _make_prompt_loader()
    run = _make_run()

    planner = ExplainMetricPlanner(client, loader)
    plan = await planner.plan(run.request_text, run)

    # normalized name must be snake_case (lowercase + underscores)
    assert plan.normalized_metric_name == plan.normalized_metric_name.lower()
    assert " " not in plan.normalized_metric_name
    assert plan.normalized_metric_name == "gross_merchandise_value"
    assert "net_revenue" in plan.related_metric_names


@pytest.mark.asyncio
async def test_plan_raises_on_invalid_json() -> None:
    from explain_metric_definition.planner import ExplainMetricPlanner

    client = _make_anthropic_client("this is not json at all")
    loader = _make_prompt_loader()
    run = _make_run()

    planner = ExplainMetricPlanner(client, loader)

    with pytest.raises(PlanningError):
        await planner.plan(run.request_text, run)
