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
        request_text="Which dashboard for weekly Germany sales?",
    )


@pytest.mark.asyncio
async def test_plan_extracts_search_terms() -> None:
    from discover_metrics_and_dashboards.planner import DiscoveryPlanner

    response_payload = {
        "search_terms": ["weekly sales", "germany"],
        "asset_types": ["dashboard"],
        "business_domain": "sales",
        "intent_summary": "The user wants to find a dashboard showing weekly sales data for Germany.",
    }

    client = _make_anthropic_client(json.dumps(response_payload))
    loader = _make_prompt_loader()
    run = _make_run()

    planner = DiscoveryPlanner(client, loader)
    plan = await planner.plan(run.request_text, run)

    assert "weekly sales" in plan.search_terms
    assert "germany" in plan.search_terms


@pytest.mark.asyncio
async def test_plan_raises_on_invalid_json() -> None:
    from discover_metrics_and_dashboards.planner import DiscoveryPlanner

    client = _make_anthropic_client("this is definitely not json")
    loader = _make_prompt_loader()
    run = _make_run()

    planner = DiscoveryPlanner(client, loader)

    with pytest.raises(PlanningError):
        await planner.plan(run.request_text, run)


@pytest.mark.asyncio
async def test_plan_sets_skill_name() -> None:
    from discover_metrics_and_dashboards.planner import DiscoveryPlanner

    response_payload = {
        "search_terms": ["contribution margin"],
        "asset_types": ["metric"],
        "business_domain": "finance",
        "intent_summary": "The user wants to find a contribution margin metric.",
    }

    client = _make_anthropic_client(json.dumps(response_payload))
    loader = _make_prompt_loader()
    run = _make_run()

    planner = DiscoveryPlanner(client, loader)
    plan = await planner.plan(run.request_text, run)

    assert plan.skill_name == "discover_metrics_and_dashboards"
