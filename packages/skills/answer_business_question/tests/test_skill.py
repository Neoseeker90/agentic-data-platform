from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from contracts.context_pack import ContextSource, SourceAuthority, SourceType
from contracts.run import Run


def _make_run() -> Run:
    return Run(
        user_id="test_user",
        interface="test",
        request_text="What is our net revenue for last quarter?",
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
    # First call returns plan_message, second returns execute_message
    client.messages.create = AsyncMock(side_effect=[plan_message, execute_message])
    return client


def _make_lightdash_search() -> MagicMock:
    source = ContextSource(
        source_type=SourceType.LIGHTDASH_METRIC,
        authority=SourceAuthority.PRIMARY,
        freshness="current",
        object_ref="net_revenue",
        label="Net Revenue",
        snippet="Total net revenue metric.",
    )
    mock = MagicMock()
    mock.find_relevant_context = AsyncMock(return_value=[source])
    return mock


def _make_dbt_reader() -> MagicMock:
    mock = MagicMock()
    mock.search_metrics = MagicMock(return_value=[])
    mock.metrics_to_context_sources = MagicMock(return_value=[])
    return mock


def _make_docs_searcher() -> MagicMock:
    mock = MagicMock()
    mock.search = AsyncMock(return_value=[])
    mock.to_context_sources = AsyncMock(return_value=[])
    return mock


@pytest.mark.asyncio
async def test_full_pipeline_happy_path() -> None:
    from answer_business_question.skill import AnswerBusinessQuestionSkill

    plan_payload = {
        "question_type": "trend",
        "identified_metrics": ["net_revenue"],
        "identified_dimensions": ["region"],
        "identified_time_range": "last quarter",
        "business_domain": "finance",
        "ambiguous_terms": [],
        "intent_summary": "User wants net revenue for last quarter by region.",
        "planning_confidence": 0.95,
    }

    execute_payload = {
        "answer_text": "## Net Revenue Last Quarter\n\nNet revenue was $10M across all regions.",
        "trusted_references": [
            {
                "ref_type": "metric",
                "name": "net_revenue",
                "url": "https://lightdash.example.com/metrics/net_revenue",
                "authority": "primary",
            }
        ],
        "confidence": 0.9,
        "caveat": None,
        "suggested_dashboards": [],
    }

    run = _make_run()
    client = _make_anthropic_client(plan_payload, execute_payload)
    loader = _make_prompt_loader()
    lightdash = _make_lightdash_search()
    dbt = _make_dbt_reader()
    docs = _make_docs_searcher()

    skill = AnswerBusinessQuestionSkill(
        anthropic_client=client,
        prompt_loader=loader,
        lightdash_search=lightdash,
        dbt_reader=dbt,
        docs_searcher=docs,
    )

    # Step 1: Plan
    plan = await skill.plan(run.request_text, run)
    assert plan.run_id == run.run_id
    assert "net_revenue" in plan.identified_metrics

    # Step 2: Build context
    context = await skill.build_context(plan, run)
    assert len(context.sources) > 0

    # Step 3: Validate
    validation = await skill.validate(plan, context)
    assert validation.passed is True
    assert validation.requires_approval is False

    # Step 4: Execute
    exec_result = await skill.execute(plan, context)
    assert exec_result.success is True
    assert exec_result.run_id == run.run_id

    # Step 5: Format
    formatted = await skill.format_result(exec_result)
    assert isinstance(formatted, str)
    assert len(formatted) > 0
    assert "Net Revenue" in formatted
