from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from typing import Any

from contracts.run import Run
from skill_sdk.exceptions import PlanningError
from skill_sdk.json_utils import parse_llm_json

from .models import AssetType, DiscoveryPlan

logger = logging.getLogger(__name__)

_PROMPT_NAME = "plan_discovery_v1"
_DEFAULT_MODEL_ID = "claude-3-5-haiku-20241022"
_MAX_TOKENS = 1024


class DiscoveryPlanner:
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
    ) -> DiscoveryPlan:
        prompt = self._prompt_loader.render(
            _PROMPT_NAME,
            request_text=request_text,
        )
        prompt_version_id = self._prompt_loader.get_version_id(_PROMPT_NAME)

        logger.debug("Calling LLM for discovery planning run_id=%s", run.run_id)

        _t0 = time.monotonic()
        try:
            response = await self._client.messages.create(
                model=self._model_id,
                max_tokens=_MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            raise PlanningError(f"LLM call failed during planning: {exc}") from exc
        _latency_ms = int((time.monotonic() - _t0) * 1000)

        if self._cost_recorder is not None:
            await self._cost_recorder.record(
                run_id=run.run_id,
                stage="planning",
                skill_name="discover_metrics_and_dashboards",
                provider="bedrock",
                model_id=self._model_id,
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                latency_ms=_latency_ms,
            )

        raw_text = response.content[0].text
        logger.debug("DiscoveryPlanner LLM raw response: %s", raw_text)

        try:
            raw = parse_llm_json(raw_text)
        except json.JSONDecodeError as exc:
            raise PlanningError(
                f"DiscoveryPlanner LLM returned non-JSON output: {raw_text!r}"
            ) from exc

        try:
            raw_asset_types = raw.get("asset_types", [])
            asset_types: list[AssetType] = []
            for at in raw_asset_types:
                try:
                    asset_types.append(AssetType(at))
                except ValueError:
                    logger.warning("Unknown asset_type from LLM: %r — skipping", at)

            plan = DiscoveryPlan(
                run_id=run.run_id,
                intent_summary=raw.get("intent_summary", ""),
                extracted_entities={
                    "search_terms": raw.get("search_terms", []),
                    "asset_types": raw.get("asset_types", []),
                    "business_domain": raw.get("business_domain"),
                },
                prompt_version_id=prompt_version_id,
                model_id=self._model_id,
                planned_at=datetime.now(UTC),
                search_terms=raw.get("search_terms", []),
                asset_types=asset_types,
                business_domain=raw.get("business_domain"),
            )
        except Exception as exc:
            raise PlanningError(
                f"Failed to construct DiscoveryPlan from LLM output: {exc}"
            ) from exc

        logger.info(
            "Planned discovery run_id=%s search_terms=%s asset_types=%s",
            run.run_id,
            plan.search_terms,
            [at.value for at in plan.asset_types],
        )
        return plan
