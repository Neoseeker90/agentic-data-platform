from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from contracts.context_pack import ContextPack, ContextSource, SourceType
from contracts.execution import ExecutionResult
from skill_sdk.exceptions import ExecutionError

from .models import AssetType, DiscoveryPlan, DiscoveryResult, RankedAsset

logger = logging.getLogger(__name__)

_PROMPT_NAME = "rank_results_v1"
_DEFAULT_MODEL_ID = "claude-3-5-sonnet-20241022"
_MAX_TOKENS = 2048
_MAX_CANDIDATES = 50

# Map SourceType to AssetType
_SOURCE_TYPE_TO_ASSET_TYPE: dict[SourceType, AssetType] = {
    SourceType.LIGHTDASH_METRIC: AssetType.METRIC,
    SourceType.LIGHTDASH_DASHBOARD: AssetType.DASHBOARD,
    SourceType.LIGHTDASH_CHART: AssetType.CHART,
    SourceType.DBT_MODEL: AssetType.DBT_MODEL,
    SourceType.DBT_METRIC: AssetType.METRIC,
    SourceType.DBT_YAML: AssetType.SEMANTIC_OBJECT,
    SourceType.KPI_GLOSSARY: AssetType.METRIC,
    SourceType.BUSINESS_DOC: AssetType.SEMANTIC_OBJECT,
    SourceType.DASHBOARD_METADATA: AssetType.DASHBOARD,
}

_DASHBOARD_ASSET_TYPES = {AssetType.DASHBOARD}
_METRIC_ASSET_TYPES = {
    AssetType.METRIC,
    AssetType.CHART,
    AssetType.SEMANTIC_OBJECT,
    AssetType.DBT_MODEL,
}


def _build_candidates_text(sources: list[ContextSource]) -> str:
    """Build a newline-separated candidate list for the LLM."""
    lines: list[str] = []
    for source in sources[:_MAX_CANDIDATES]:
        desc = source.snippet or ""
        lines.append(f"- {source.object_ref}: {desc}")
    return "\n".join(lines)


class DiscoveryExecutor:
    def __init__(
        self,
        anthropic_client: Any,
        prompt_loader: Any,
        cost_recorder: Any | None = None,
        execution_model: str | None = None,
    ) -> None:
        self._client = anthropic_client
        self._model_id = execution_model or _DEFAULT_MODEL_ID
        self._prompt_loader = prompt_loader
        self._cost_recorder = cost_recorder

    async def execute(
        self,
        plan: DiscoveryPlan,
        context: ContextPack,
    ) -> ExecutionResult:
        if not context.sources:
            result = DiscoveryResult(
                ranked_metrics=[],
                ranked_dashboards=[],
                summary="No matching assets found.",
                total_found=0,
            )
            return ExecutionResult(
                run_id=plan.run_id,
                plan_id=plan.plan_id,
                success=True,
                output=result.model_dump(),
                formatted_response=None,
                executed_at=datetime.now(UTC),
            )

        candidates_text = _build_candidates_text(context.sources)
        full_query = " ".join(plan.search_terms)

        prompt = self._prompt_loader.render(
            _PROMPT_NAME,
            query=plan.intent_summary or full_query,
            candidates=candidates_text,
        )

        logger.debug("Calling LLM for ranking plan_id=%s", plan.plan_id)

        try:
            response = await self._client.messages.create(
                model=self._model_id,
                max_tokens=_MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            raise ExecutionError(f"LLM call failed during execution: {exc}") from exc

        raw_text = response.content[0].text
        logger.debug("DiscoveryExecutor LLM raw response: %s", raw_text)

        # Strip markdown code fences if the model wrapped the JSON
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]  # drop the opening ```json line
            cleaned = cleaned.rsplit("```", 1)[0]  # drop the closing ```
            cleaned = cleaned.strip()

        try:
            raw_rankings = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ExecutionError(
                f"DiscoveryExecutor LLM returned non-JSON output: {raw_text!r}"
            ) from exc

        if not isinstance(raw_rankings, list):
            raise ExecutionError(
                f"DiscoveryExecutor expected a JSON array, got: {type(raw_rankings)}"
            )

        # Build a lookup map from source object_ref -> source
        source_by_ref: dict[str, ContextSource] = {s.object_ref: s for s in context.sources}

        ranked_metrics: list[RankedAsset] = []
        ranked_dashboards: list[RankedAsset] = []

        try:
            for item in raw_rankings:
                name = item.get("name", "")
                relevance_score = float(item.get("relevance_score", 0.0))
                reason = item.get("reason", "")

                source = source_by_ref.get(name)
                if source is None:
                    logger.debug("Ranking refers to unknown asset %r — skipping", name)
                    continue

                asset_type = _SOURCE_TYPE_TO_ASSET_TYPE.get(
                    source.source_type, AssetType.SEMANTIC_OBJECT
                )
                url = source.metadata.get("url")
                description = source.snippet or None

                ranked_asset = RankedAsset(
                    asset_type=asset_type,
                    name=name,
                    description=description,
                    relevance_score=max(0.0, min(1.0, relevance_score)),
                    url=url,
                    authority=source.authority,
                    reason=reason,
                )

                if asset_type in _DASHBOARD_ASSET_TYPES:
                    ranked_dashboards.append(ranked_asset)
                else:
                    ranked_metrics.append(ranked_asset)
        except Exception as exc:
            raise ExecutionError(
                f"Failed to construct RankedAsset objects from LLM output: {exc}"
            ) from exc

        # Sort by relevance_score descending
        ranked_metrics.sort(key=lambda a: a.relevance_score, reverse=True)
        ranked_dashboards.sort(key=lambda a: a.relevance_score, reverse=True)

        total_found = len(ranked_metrics) + len(ranked_dashboards)
        summary = (
            f"Found {total_found} relevant asset(s): "
            f"{len(ranked_metrics)} metric/model(s), "
            f"{len(ranked_dashboards)} dashboard(s)."
        )

        result = DiscoveryResult(
            ranked_metrics=ranked_metrics,
            ranked_dashboards=ranked_dashboards,
            summary=summary,
            total_found=total_found,
        )

        logger.info(
            "Executed discovery plan_id=%s total_found=%d",
            plan.plan_id,
            total_found,
        )

        return ExecutionResult(
            run_id=plan.run_id,
            plan_id=plan.plan_id,
            success=True,
            output=result.model_dump(),
            formatted_response=None,
            executed_at=datetime.now(UTC),
        )
