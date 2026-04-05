from __future__ import annotations

import json
import logging

from contracts.context_pack import ContextPack, ContextSource, SourceAuthority, SourceType
from contracts.run import Run
from lightdash_adapter.client import LightdashClient

from .models import DataQueryPlan

logger = logging.getLogger(__name__)


class DataQueryContextBuilder:
    def __init__(self, lightdash_client: LightdashClient) -> None:
        self._lightdash_client = lightdash_client

    async def build_context(
        self,
        plan: DataQueryPlan,
        run: Run,
    ) -> ContextPack:
        if not plan.explore_name:
            logger.warning("build_context called with empty explore_name for run_id=%s", run.run_id)
            return ContextPack(
                run_id=run.run_id,
                plan_id=plan.plan_id,
                skill_name=plan.skill_name,
                sources=[],
                unresolved_ambiguities=["No explore name specified in plan."],
            )

        # Fetch explore detail for the planned explore
        try:
            explore_detail = await self._lightdash_client.get_explore_detail(plan.explore_name)
        except Exception as exc:
            logger.warning("Failed to fetch explore detail for %s: %s", plan.explore_name, exc)
            return ContextPack(
                run_id=run.run_id,
                plan_id=plan.plan_id,
                skill_name=plan.skill_name,
                sources=[],
                unresolved_ambiguities=[f"Failed to retrieve explore '{plan.explore_name}': {exc}"],
            )

        # Build a map from field_id to field for quick lookup
        field_map = {field.field_id: field for field in explore_detail.fields}

        # Create ContextSource entries for each requested field
        all_field_ids = list(dict.fromkeys(plan.dimensions + plan.metrics))  # preserve order, deduplicate
        sources: list[ContextSource] = []

        for idx, field_id in enumerate(all_field_ids):
            field = field_map.get(field_id)
            if field is None:
                logger.warning("Field %s not found in explore %s", field_id, plan.explore_name)
                continue

            metadata: dict = {
                "field_id": field.field_id,
                "field_type": field.field_type,
                "type": field.type,
                "explore_name": plan.explore_name,
            }

            # Attach the full explore_detail JSON to the first source's metadata
            if idx == 0:
                metadata["explore_detail"] = explore_detail.model_dump()

            sources.append(
                ContextSource(
                    source_type=SourceType.LIGHTDASH_METRIC
                    if field.field_type == "metric"
                    else SourceType.LIGHTDASH_CHART,
                    authority=SourceAuthority.PRIMARY,
                    freshness="current",
                    object_ref=field_id,
                    label=field.label,
                    snippet=field.description or field.label,
                    metadata=metadata,
                )
            )

        # If no fields matched but explore_detail was fetched, still attach it so the validator can check
        if not sources:
            sources.append(
                ContextSource(
                    source_type=SourceType.LIGHTDASH_METRIC,
                    authority=SourceAuthority.PRIMARY,
                    freshness="current",
                    object_ref=plan.explore_name,
                    label=explore_detail.label,
                    snippet=explore_detail.description or explore_detail.label,
                    metadata={"explore_detail": explore_detail.model_dump()},
                )
            )

        logger.info(
            "Built context pack for run_id=%s: %d field sources from explore %s",
            run.run_id,
            len(sources),
            plan.explore_name,
        )

        return ContextPack(
            run_id=run.run_id,
            plan_id=plan.plan_id,
            skill_name=plan.skill_name,
            sources=sources,
            unresolved_ambiguities=[],
        )
