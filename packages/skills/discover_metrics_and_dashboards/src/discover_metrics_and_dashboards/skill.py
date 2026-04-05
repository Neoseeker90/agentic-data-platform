from __future__ import annotations

from typing import Any

from business_docs_adapter.pg_fts import PgFtsSearcher
from contracts.context_pack import ContextPack
from contracts.execution import ExecutionResult
from contracts.plan import BasePlan
from contracts.run import Run
from contracts.validation import ValidationResult
from dbt_adapter.manifest_reader import DbtManifestReader
from lightdash_adapter.search import LightdashSearchService
from skill_sdk.base import Skill

from .context_builder import DiscoveryContextBuilder
from .executor import DiscoveryExecutor
from .formatter import DiscoveryFormatter
from .models import DiscoveryPlan
from .planner import DiscoveryPlanner
from .validator import DiscoveryValidator


class DiscoverMetricsAndDashboardsSkill(Skill):
    name = "discover_metrics_and_dashboards"
    description = (
        "Find and navigate to existing metrics, dashboards, and analytics assets. "
        "Use when the user wants to discover what exists rather than get an answer."
    )
    risk_level = "read_only"
    version = "1.0.0"

    def __init__(
        self,
        anthropic_client: Any,
        prompt_loader: Any,
        lightdash_search: LightdashSearchService,
        dbt_reader: DbtManifestReader,
        docs_searcher: PgFtsSearcher,
        cost_recorder: Any | None = None,
        planning_model: str | None = None,
        execution_model: str | None = None,
    ) -> None:
        self._planner = DiscoveryPlanner(
            anthropic_client, prompt_loader, cost_recorder, planning_model=planning_model
        )
        self._context_builder = DiscoveryContextBuilder(lightdash_search, dbt_reader, docs_searcher)
        self._validator = DiscoveryValidator()
        self._executor = DiscoveryExecutor(
            anthropic_client, prompt_loader, cost_recorder, execution_model=execution_model
        )
        self._formatter = DiscoveryFormatter()

    async def plan(
        self,
        request_text: str,
        run: Run,
        context: dict | None = None,
    ) -> DiscoveryPlan:
        return await self._planner.plan(request_text, run, context)

    async def build_context(
        self,
        plan: BasePlan,
        run: Run,
        context: dict | None = None,
    ) -> ContextPack:
        assert isinstance(plan, DiscoveryPlan)
        return await self._context_builder.build_context(plan, run)

    async def validate(
        self,
        plan: BasePlan,
        built_context: ContextPack,
    ) -> ValidationResult:
        assert isinstance(plan, DiscoveryPlan)
        return await self._validator.validate(plan, built_context)

    async def execute(
        self,
        plan: BasePlan,
        built_context: ContextPack,
    ) -> ExecutionResult:
        assert isinstance(plan, DiscoveryPlan)
        return await self._executor.execute(plan, built_context)

    async def format_result(self, result: ExecutionResult) -> str:
        return self._formatter.format_result(result)
