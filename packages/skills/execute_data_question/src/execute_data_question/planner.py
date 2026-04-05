from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from contracts.run import Run
from lightdash_adapter.client import LightdashClient
from skill_sdk.exceptions import ClarificationNeeded, PlanningError
from skill_sdk.json_utils import parse_llm_json

from .models import DataQueryPlan

logger = logging.getLogger(__name__)

_PROMPT_NAME = "plan_data_query_v1"
_DEFAULT_MODEL_ID = "claude-3-haiku-20240307"
_MAX_TOKENS = 2048
_MAX_CATALOGUE_CHARS = 12000
_MAX_EXPLORES = 3


def _keyword_score(text: str, query_words: set[str]) -> int:
    """Return the number of query words found in text (case-insensitive)."""
    text_lower = text.lower()
    return sum(1 for word in query_words if word in text_lower)


def _build_catalogue(explore_details: list[Any]) -> str:
    """Build a text catalogue of explores and their fields, with metrics and dimensions separated."""
    lines: list[str] = []
    for detail in explore_details:
        lines.append(f"## Explore: {detail.explore_name} ({detail.label})")
        if detail.description:
            lines.append(f"   Description: {detail.description}")

        metrics = [f for f in detail.fields if f.field_type == "metric"]
        dimensions = [f for f in detail.fields if f.field_type == "dimension"]

        lines.append(
            "   METRICS (use these in the 'metrics' array — these are aggregated measures):"
        )
        if metrics:
            for field in metrics:
                desc = f" — {field.description[:80]}" if field.description else ""
                lines.append(f"     - {field.field_id} | {field.label}{desc}")
        else:
            lines.append("     (none)")

        lines.append(
            "   DIMENSIONS (use these in the 'dimensions' array — these are grouping/filter fields):"
        )
        for field in dimensions[:40]:  # cap dimensions to keep prompt size reasonable
            lines.append(f"     - {field.field_id} | {field.label} | type={field.type}")
        if len(dimensions) > 40:
            lines.append(f"     ... ({len(dimensions) - 40} more dimensions not shown)")
        lines.append("")
    return "\n".join(lines)


class DataQueryPlanner:
    def __init__(
        self,
        anthropic_client: Any,
        prompt_loader: Any,
        lightdash_client: LightdashClient,
        cost_recorder: Any | None = None,
        planning_model: str | None = None,
    ) -> None:
        self._client = anthropic_client
        self._model_id = planning_model or _DEFAULT_MODEL_ID
        self._prompt_loader = prompt_loader
        self._lightdash_client = lightdash_client
        self._cost_recorder = cost_recorder

    async def plan(
        self,
        request_text: str,
        run: Run,
        context: dict | None = None,
    ) -> DataQueryPlan:
        # Step 1: Fetch all explores (summary list)
        try:
            all_explores = await self._lightdash_client.list_explores()
        except Exception as exc:
            logger.warning("Failed to list explores from Lightdash: %s", exc)
            return DataQueryPlan(
                run_id=run.run_id,
                intent_summary="Failed to retrieve explore metadata.",
                planning_confidence=0.0,
            )

        # Step 2: Keyword-match explore names/labels against request_text
        query_words = set(request_text.lower().split())
        scored = []
        for explore in all_explores:
            score = _keyword_score(explore.get("name", ""), query_words)
            score += _keyword_score(explore.get("label", ""), query_words)
            scored.append((score, explore))

        scored.sort(key=lambda x: x[0], reverse=True)

        # Step 3: Fetch detail for top _MAX_EXPLORES matching explores
        if scored and scored[0][0] > 0:
            top_explores = [e for _, e in scored[:_MAX_EXPLORES]]
        else:
            # Fall back to all explores (up to _MAX_EXPLORES)
            top_explores = [e for _, e in scored[:_MAX_EXPLORES]]

        explore_details = []
        for explore in top_explores:
            try:
                detail = await self._lightdash_client.get_explore_detail(explore["name"])
                explore_details.append(detail)
            except Exception as exc:
                logger.warning("Failed to fetch explore detail for %s: %s", explore["name"], exc)

        if not explore_details:
            logger.warning("No explore details could be fetched from Lightdash")
            return DataQueryPlan(
                run_id=run.run_id,
                intent_summary="No explore details available.",
                planning_confidence=0.0,
            )

        # Step 4: Build catalogue string
        catalogue = _build_catalogue(explore_details)

        # Step 5: Truncate catalogue to _MAX_CATALOGUE_CHARS
        if len(catalogue) > _MAX_CATALOGUE_CHARS:
            catalogue = catalogue[:_MAX_CATALOGUE_CHARS] + "\n... (catalogue truncated)"

        # Step 6: Render prompt
        prompt = self._prompt_loader.render(
            _PROMPT_NAME,
            request_text=request_text,
            explore_catalogue=catalogue,
        )
        prompt_version_id = self._prompt_loader.get_version_id(_PROMPT_NAME)

        logger.debug("Calling LLM for planning run_id=%s", run.run_id)

        # Step 7: Call LLM
        try:
            response = await self._client.messages.create(
                model=self._model_id,
                max_tokens=_MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            raise PlanningError(f"LLM call failed during planning: {exc}") from exc

        raw_text = response.content[0].text
        logger.debug("Planner LLM raw response: %s", raw_text)

        # Step 8: Strip code fences, parse JSON
        try:
            raw = parse_llm_json(raw_text)
        except json.JSONDecodeError as exc:
            raise PlanningError(f"Planner LLM returned non-JSON output: {raw_text!r}") from exc

        # Step 8b: Check if the LLM returned a clarification request instead of a plan
        if raw.get("type") == "clarification":
            question = raw.get("question", "Could you provide more details?")
            raise ClarificationNeeded(question)

        # Step 9: Construct DataQueryPlan from parsed dict
        try:
            intent_summary = raw.get("intent_summary", "")
            plan = DataQueryPlan(
                run_id=run.run_id,
                intent_summary=intent_summary,
                extracted_entities={
                    "explore_name": raw.get("explore_name", ""),
                    "dimensions": raw.get("dimensions", []),
                    "metrics": raw.get("metrics", []),
                    "answer_type": raw.get("answer_type", "table"),
                },
                prompt_version_id=prompt_version_id,
                model_id=self._model_id,
                planned_at=datetime.now(UTC),
                explore_name=raw.get("explore_name", ""),
                dimensions=raw.get("dimensions", []),
                metrics=raw.get("metrics", []),
                filters=raw.get("filters", {}),
                sorts=raw.get("sorts", []),
                limit=raw.get("limit", 100),
                answer_type=raw.get("answer_type", "table"),
                chart_title=raw.get("chart_title", ""),
                planning_confidence=raw.get("planning_confidence", 1.0),
            )
        except Exception as exc:
            raise PlanningError(
                f"Failed to construct DataQueryPlan from LLM output: {exc}"
            ) from exc

        logger.info(
            "Planned run_id=%s explore=%r answer_type=%r confidence=%.2f",
            run.run_id,
            plan.explore_name,
            plan.answer_type,
            plan.planning_confidence,
        )
        return plan
