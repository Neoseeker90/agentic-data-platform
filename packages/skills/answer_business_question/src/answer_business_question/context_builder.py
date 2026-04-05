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

from .models import BusinessQuestionPlan

logger = logging.getLogger(__name__)

_MAX_SOURCES = 20


class BusinessQuestionContextBuilder:
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
        plan: BusinessQuestionPlan,
        run: Run,
    ) -> ContextPack:
        tasks: list[Any] = []

        # 1. Per-metric searches
        for metric in plan.identified_metrics:
            tasks.append(self._lightdash.find_relevant_context(metric))
            tasks.append(self._dbt_metric_sources(metric))

        # 2. Per-dimension searches
        for dimension in plan.identified_dimensions:
            tasks.append(self._lightdash.find_relevant_context(dimension))

        # 3. Full request text against docs (KPI_GLOSSARY + BUSINESS_LOGIC)
        request_text = run.request_text
        tasks.append(self._docs_sources(request_text, DocType.KPI_GLOSSARY))
        tasks.append(self._docs_sources(request_text, DocType.BUSINESS_LOGIC))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_sources: list[ContextSource] = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Context retrieval subtask failed: %s", result)
                continue
            all_sources.extend(result)  # type: ignore

        # 4. Deduplicate by object_ref (keep first seen)
        seen_refs: set[str] = set()
        deduped: list[ContextSource] = []
        for source in all_sources:
            if source.object_ref not in seen_refs:
                seen_refs.add(source.object_ref)
                deduped.append(source)

        # 5. Cap at MAX_SOURCES
        capped = deduped[:_MAX_SOURCES]

        # 6. Identify unresolved ambiguities
        unresolved: list[str] = []
        for term in plan.ambiguous_terms:
            term_lower = term.lower()
            matched = any(
                term_lower in s.object_ref.lower() or term_lower in s.label.lower() for s in capped
            )
            if not matched:
                unresolved.append(term)

        logger.info(
            "Built context pack for run_id=%s: %d sources, %d unresolved ambiguities",
            run.run_id,
            len(capped),
            len(unresolved),
        )

        return ContextPack(
            run_id=run.run_id,
            plan_id=plan.plan_id,
            skill_name=plan.skill_name,
            sources=capped,
            unresolved_ambiguities=unresolved,
        )

    async def _dbt_metric_sources(self, metric: str) -> list[ContextSource]:
        metrics = self._dbt.search_metrics(metric)
        return self._dbt.metrics_to_context_sources(metrics)

    async def _docs_sources(self, query: str, doc_type: DocType) -> list[ContextSource]:
        results = await self._docs.search(query, doc_type=doc_type)
        return await self._docs.to_context_sources(results)
