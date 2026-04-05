from __future__ import annotations

from typing import Any

from contracts.context_pack import ContextPack
from contracts.execution import ExecutionResult
from contracts.plan import BasePlan
from contracts.run import Run
from contracts.validation import ValidationResult
from lightdash_adapter.chart_uploader import ChartUploader
from lightdash_adapter.client import LightdashClient
from skill_sdk.base import Skill

from .context_builder import DataQueryContextBuilder
from .executor import DataQueryExecutor
from .formatter import DataQueryFormatter
from .models import DataQueryPlan
from .planner import DataQueryPlanner
from .validator import DataQueryValidator


class ExecuteDataQuestionSkill(Skill):
    name = "execute_data_question"
    description = (
        "Execute data queries against Lightdash to retrieve actual numbers, tables, or charts. "
        "Use when the user asks for specific data values, trends, rankings, or wants to see "
        "real computed data from the warehouse."
    )
    risk_level = "read_only"
    version = "1.0.0"

    def __init__(
        self,
        anthropic_client: Any,
        prompt_loader: Any,
        lightdash_client: LightdashClient,
        cost_recorder: Any | None = None,
        planning_model: str | None = None,
        execution_model: str | None = None,
        dbt_project_path: str = "",
    ) -> None:
        self._planner = DataQueryPlanner(
            anthropic_client,
            prompt_loader,
            lightdash_client,
            cost_recorder,
            planning_model=planning_model,
        )
        self._context_builder = DataQueryContextBuilder(lightdash_client)
        self._validator = DataQueryValidator()

        # Build ChartUploader if dbt_project_path and lightdash settings are available
        chart_uploader: ChartUploader | None = None
        lightdash_url = getattr(lightdash_client, "_client", None)
        if dbt_project_path and lightdash_url is not None:
            base_url = str(lightdash_client._client.base_url).rstrip("/")
            project_uuid = lightdash_client._project_uuid
            if base_url and project_uuid:
                api_key = getattr(lightdash_client._client, "headers", {}).get(
                    "authorization", ""
                ).replace("ApiKey ", "")
                chart_uploader = ChartUploader(
                    lightdash_url=base_url,
                    project_uuid=project_uuid,
                    dbt_project_path=dbt_project_path,
                    api_key=api_key,
                )

        self._executor = DataQueryExecutor(
            anthropic_client,
            prompt_loader,
            lightdash_client,
            cost_recorder,
            execution_model=execution_model,
            chart_uploader=chart_uploader,
        )
        self._formatter = DataQueryFormatter()

    async def plan(
        self,
        request_text: str,
        run: Run,
        context: dict | None = None,
    ) -> DataQueryPlan:
        return await self._planner.plan(request_text, run, context)

    async def build_context(
        self,
        plan: BasePlan,
        run: Run,
        context: dict | None = None,
    ) -> ContextPack:
        assert isinstance(plan, DataQueryPlan)
        return await self._context_builder.build_context(plan, run)

    async def validate(
        self,
        plan: BasePlan,
        built_context: ContextPack,
    ) -> ValidationResult:
        assert isinstance(plan, DataQueryPlan)
        return await self._validator.validate(plan, built_context)

    async def execute(
        self,
        plan: BasePlan,
        built_context: ContextPack,
    ) -> ExecutionResult:
        assert isinstance(plan, DataQueryPlan)
        return await self._executor.execute(plan, built_context)

    async def format_result(self, result: ExecutionResult) -> str:
        return self._formatter.format_result(result)
