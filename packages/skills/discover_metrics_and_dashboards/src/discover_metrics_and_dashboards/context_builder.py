from __future__ import annotations

import asyncio
import logging
from typing import Any

from business_docs_adapter.models import DocType
from business_docs_adapter.pg_fts import PgFtsSearcher
from contracts.context_pack import ContextPack, ContextSource
from contracts.run import Run
from dbt_adapter.manifest_reader import DbtManifestReader
from lightdash_adapter.client import LightdashClient
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
        lightdash_client: LightdashClient | None = None,
        semantic_search: Any | None = None,
    ) -> None:
        self._lightdash = lightdash_search
        self._lightdash_client = lightdash_client
        self._dbt = dbt_reader
        self._docs = docs_searcher
        self._semantic_search = semantic_search
        self._explore_names: list[str] | None = None  # cached on first use

    async def _semantic_or_keyword(self, term: str) -> list[ContextSource]:
        """Try semantic vector search. Falls back to keyword if unavailable or empty."""
        if self._semantic_search is not None:
            try:
                from vector_store.models import ContentType  # noqa: PLC0415

                results = await self._semantic_search.search(
                    term,
                    content_types=[
                        ContentType.DBT_METRIC,
                        ContentType.DBT_MODEL,
                        ContentType.LIGHTDASH_DASHBOARD,
                        ContentType.LIGHTDASH_FIELD,
                    ],
                    max_results=10,
                )
                if results:
                    return results
            except Exception as exc:
                logger.warning("Semantic search failed, using keyword: %s", exc)
        # Keyword fallback
        ls, dbt = await asyncio.gather(
            self._lightdash.find_relevant_context(term),
            self._dbt_metric_sources(term),
            return_exceptions=True,
        )
        sources: list[ContextSource] = []
        for r in (ls, dbt):
            if isinstance(r, Exception):
                logger.warning("Keyword search subtask failed: %s", r)
            else:
                sources.extend(r)  # type: ignore
        return sources

    async def build_context(
        self,
        plan: DiscoveryPlan,
        run: Run,
    ) -> ContextPack:
        tasks: list[Any] = []

        # Per search_term: semantic search with keyword fallback.
        # dbt model search is intentionally excluded from discovery — keyword
        # matching on model names returns unrelated monitoring/infra models.
        # Instead we add the Lightdash-exposed models once (not per term).
        for term in plan.search_terms:
            tasks.append(self._semantic_or_keyword(term))

        # Add dbt models for the explores Lightdash actually exposes
        tasks.append(self._lightdash_explore_model_sources())

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

    async def _lightdash_explore_model_sources(self) -> list[ContextSource]:
        """Return dbt context sources only for models exposed in Lightdash explores."""
        if self._lightdash_client is None:
            return []

        # Cache explore names for the lifetime of this skill instance
        if self._explore_names is None:
            try:
                explores = await self._lightdash_client.list_explores()
                self._explore_names = [e["name"] for e in explores]
            except Exception as exc:
                logger.warning("Failed to fetch Lightdash explores: %s", exc)
                self._explore_names = []

        sources: list[ContextSource] = []
        for name in self._explore_names:
            model = self._dbt.get_model(name)
            if model:
                sources.extend(self._dbt.to_context_sources([model]))
        return sources

    async def _dbt_metric_sources(self, term: str) -> list[ContextSource]:
        metrics = self._dbt.search_metrics(term)
        return self._dbt.metrics_to_context_sources(metrics)

    async def _docs_sources(self, query: str, doc_type: DocType) -> list[ContextSource]:
        results = await self._docs.search(query, doc_type=doc_type)
        return await self._docs.to_context_sources(results)
