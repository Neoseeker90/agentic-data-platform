from __future__ import annotations

import asyncio
import logging
from typing import Any

from business_docs_adapter.models import DocType
from business_docs_adapter.pg_fts import PgFtsSearcher
from contracts.context_pack import ContextPack, ContextSource
from contracts.run import Run
from dbt_adapter.manifest_reader import DbtManifestReader
from lightdash_adapter.search import LightdashSearchService

from .models import DiscoveryPlan

logger = logging.getLogger(__name__)

_MAX_SOURCES = 30


class DiscoveryContextBuilder:
    def __init__(
        self,
        lightdash_search: LightdashSearchService,
        dbt_reader: DbtManifestReader,
        docs_searcher: PgFtsSearcher,
    ) -> None:
        self._lightdash = lightdash_search
        self._dbt = dbt_reader
        self._docs = docs_searcher

    async def build_context(
        self,
        plan: DiscoveryPlan,
        run: Run,
    ) -> ContextPack:
        tasks: list[Any] = []

        # Per search_term: Lightdash, dbt models, dbt metrics
        for term in plan.search_terms:
            tasks.append(self._lightdash.find_relevant_context(term))
            tasks.append(self._dbt_model_sources(term))
            tasks.append(self._dbt_metric_sources(term))

        # Full query against KPI glossary docs
        full_query = " ".join(plan.search_terms)
        tasks.append(self._docs_sources(full_query, DocType.KPI_GLOSSARY))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_sources: list[ContextSource] = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Context retrieval subtask failed: %s", result)
                continue
            all_sources.extend(result)  # type: ignore

        # Deduplicate by object_ref (keep first seen)
        seen_refs: set[str] = set()
        deduped: list[ContextSource] = []
        for source in all_sources:
            if source.object_ref not in seen_refs:
                seen_refs.add(source.object_ref)
                deduped.append(source)

        # Cap at MAX_SOURCES
        capped = deduped[:_MAX_SOURCES]

        logger.info(
            "Built discovery context pack for run_id=%s: %d sources",
            run.run_id,
            len(capped),
        )

        return ContextPack(
            run_id=run.run_id,
            plan_id=plan.plan_id,
            skill_name=plan.skill_name,
            sources=capped,
        )

    async def _dbt_model_sources(self, term: str) -> list[ContextSource]:
        models = self._dbt.search_models(term)
        return self._dbt.to_context_sources(models)

    async def _dbt_metric_sources(self, term: str) -> list[ContextSource]:
        metrics = self._dbt.search_metrics(term)
        return self._dbt.metrics_to_context_sources(metrics)

    async def _docs_sources(self, query: str, doc_type: DocType) -> list[ContextSource]:
        results = await self._docs.search(query, doc_type=doc_type)
        return await self._docs.to_context_sources(results)
