from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from contracts.run import Run
from skill_sdk.exceptions import PlanningError

# Ensure the prompts directory is discoverable by using an absolute path
_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _make_prompt_loader() -> MagicMock:
    loader = MagicMock()
    loader.render.return_value = "rendered prompt"
    loader.get_version_id.return_value = "abc123"
    return loader


def _make_anthropic_client(response_text: str) -> AsyncMock:
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
        request_text="What is our net revenue for last quarter?",
    )


@pytest.mark.asyncio
async def test_plan_extracts_metrics() -> None:
    from answer_business_question.planner import BusinessQuestionPlanner

    response_payload = {
        "question_type": "trend",
        "identified_metrics": ["net_revenue"],
        "identified_dimensions": ["region"],
        "identified_time_range": "last quarter",
        "business_domain": "finance",
        "ambiguous_terms": [],
        "intent_summary": "User wants net revenue for last quarter by region.",
        "planning_confidence": 0.95,
    }

    client = _make_anthropic_client(json.dumps(response_payload))
    loader = _make_prompt_loader()
    run = _make_run()

    planner = BusinessQuestionPlanner(client, loader)
    plan = await planner.plan(run.request_text, run)

    assert "net_revenue" in plan.identified_metrics
    assert plan.question_type == "trend"
    assert plan.planning_confidence == pytest.approx(0.95)


@pytest.mark.asyncio
async def test_plan_raises_on_invalid_json() -> None:
    from answer_business_question.planner import BusinessQuestionPlanner

    client = _make_anthropic_client("this is not json at all")
    loader = _make_prompt_loader()
    run = _make_run()

    planner = BusinessQuestionPlanner(client, loader)

    with pytest.raises(PlanningError):
        await planner.plan(run.request_text, run)


@pytest.mark.asyncio
async def test_plan_sets_run_id() -> None:
    from answer_business_question.planner import BusinessQuestionPlanner

    response_payload = {  # type: ignore
        "question_type": "general",
        "identified_metrics": [],
        "identified_dimensions": [],
        "identified_time_range": None,
        "business_domain": None,
        "ambiguous_terms": [],
        "intent_summary": "General question.",
        "planning_confidence": 0.8,
    }

    client = _make_anthropic_client(json.dumps(response_payload))
    loader = _make_prompt_loader()
    run = _make_run()

    planner = BusinessQuestionPlanner(client, loader)
    plan = await planner.plan(run.request_text, run)

    assert plan.run_id == run.run_id
