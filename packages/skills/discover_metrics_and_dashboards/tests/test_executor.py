from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from contracts.context_pack import ContextPack, ContextSource, SourceAuthority, SourceType
from contracts.run import Run


def _make_prompt_loader() -> MagicMock:
    loader = MagicMock()
    loader.render.return_value = "rendered prompt"
    loader.get_version_id.return_value = "deadbeef"
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
        request_text="Find metrics for contribution margin",
    )


def _make_discovery_plan(run: Run):
    from discover_metrics_and_dashboards.models import AssetType, DiscoveryPlan

    return DiscoveryPlan(
        run_id=run.run_id,
        intent_summary="Find contribution margin metrics",
        search_terms=["contribution margin"],
        asset_types=[AssetType.METRIC],
        business_domain="finance",
        planned_at=datetime.now(UTC),
    )


def _make_empty_context(run: Run, plan) -> ContextPack:
    return ContextPack(
        run_id=run.run_id,
        plan_id=plan.plan_id,
        skill_name="discover_metrics_and_dashboards",
        sources=[],
    )


def _make_context_with_metric(run: Run, plan) -> ContextPack:
    source = ContextSource(
        source_type=SourceType.LIGHTDASH_METRIC,
        authority=SourceAuthority.PRIMARY,
        freshness="current",
        object_ref="contribution_margin",
        label="Contribution Margin",
        snippet="Contribution margin metric showing revenue minus variable costs.",
        metadata={"url": "https://lightdash.example.com/metrics/contribution_margin"},
    )
    return ContextPack(
        run_id=run.run_id,
        plan_id=plan.plan_id,
        skill_name="discover_metrics_and_dashboards",
        sources=[source],
    )


@pytest.mark.asyncio
async def test_executor_returns_empty_result_when_no_candidates() -> None:
    from discover_metrics_and_dashboards.executor import DiscoveryExecutor

    client = _make_anthropic_client("[]")  # LLM not actually called for empty context
    loader = _make_prompt_loader()
    run = _make_run()
    plan = _make_discovery_plan(run)
    context = _make_empty_context(run, plan)

    executor = DiscoveryExecutor(client, loader)
    result = await executor.execute(plan, context)

    assert result.success is True
    assert result.output["total_found"] == 0
    assert "No matching assets" in result.output["summary"]


@pytest.mark.asyncio
async def test_executor_parses_ranked_assets() -> None:
    from discover_metrics_and_dashboards.executor import DiscoveryExecutor

    rankings = [
        {
            "name": "contribution_margin",
            "relevance_score": 0.95,
            "reason": "Directly matches the contribution margin metric request.",
        }
    ]

    client = _make_anthropic_client(json.dumps(rankings))
    loader = _make_prompt_loader()
    run = _make_run()
    plan = _make_discovery_plan(run)
    context = _make_context_with_metric(run, plan)

    executor = DiscoveryExecutor(client, loader)
    result = await executor.execute(plan, context)

    assert result.success is True
    assert result.output["total_found"] > 0

    from discover_metrics_and_dashboards.models import DiscoveryResult

    discovery = DiscoveryResult.model_validate(result.output)
    assert len(discovery.ranked_metrics) == 1
    assert discovery.ranked_metrics[0].name == "contribution_margin"
    assert discovery.ranked_metrics[0].relevance_score == pytest.approx(0.95)
