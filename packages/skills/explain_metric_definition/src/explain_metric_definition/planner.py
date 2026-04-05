from __future__ import annotations

import json
from skill_sdk.json_utils import parse_llm_json
import logging
from datetime import UTC, datetime
from typing import Any

from contracts.run import Run
from skill_sdk.exceptions import PlanningError

from .models import ExplainMetricPlan

logger = logging.getLogger(__name__)

_PROMPT_NAME = "plan_explain_v1"
_DEFAULT_MODEL_ID = "claude-3-5-haiku-20241022"
_MAX_TOKENS = 512


class ExplainMetricPlanner:
    def __init__(
        self,
        anthropic_client: Any,
        prompt_loader: Any,
        cost_recorder: Any | None = None,
        planning_model: str | None = None,
    ) -> None:
        self._client = anthropic_client
        self._model_id = planning_model or _DEFAULT_MODEL_ID
        self._prompt_loader = prompt_loader
        self._cost_recorder = cost_recorder

    async def plan(
        self,
        request_text: str,
        run: Run,
        context: dict | None = None,
    ) -> ExplainMetricPlan:
        prompt = self._prompt_loader.render(
            _PROMPT_NAME,
            request_text=request_text,
        )
        prompt_version_id = self._prompt_loader.get_version_id(_PROMPT_NAME)

        logger.debug("Calling LLM for planning run_id=%s", run.run_id)

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

        try:
            raw = parse_llm_json(raw_text)
        except json.JSONDecodeError as exc:
            raise PlanningError(
                f"Planner LLM returned non-JSON output: {raw_text!r}"
            ) from exc

        try:
            plan = ExplainMetricPlan(
                run_id=run.run_id,
                intent_summary=raw.get("intent_summary", ""),
                extracted_entities={
                    "metric_name": raw.get("metric_name", ""),
                    "normalized_metric_name": raw.get("normalized_metric_name", ""),
                    "related_metric_names": raw.get("related_metric_names", []),
                    "business_domain": raw.get("business_domain"),
                },
                prompt_version_id=prompt_version_id,
                model_id=self._model_id,
                planned_at=datetime.now(UTC),
                metric_name=raw.get("metric_name", ""),
                normalized_metric_name=raw.get("normalized_metric_name", ""),
                related_metric_names=raw.get("related_metric_names", []),
                business_domain=raw.get("business_domain"),
            )
        except Exception as exc:
            raise PlanningError(
                f"Failed to construct ExplainMetricPlan from LLM output: {exc}"
            ) from exc

        logger.info(
            "Planned run_id=%s metric_name=%r normalized=%r",
            run.run_id,
            plan.metric_name,
            plan.normalized_metric_name,
        )
        return plan
