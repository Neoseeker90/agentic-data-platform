from __future__ import annotations

import asyncio
import logging

from business_docs_adapter.models import DocType
from business_docs_adapter.pg_fts import PgFtsSearcher
from contracts.context_pack import ContextPack, ContextSource, SourceAuthority, SourceType
from contracts.run import Run
from dbt_adapter.manifest_reader import DbtManifestReader
from lightdash_adapter.client import LightdashClient
from lightdash_adapter.search import LightdashSearchService

from .models import ExplainMetricPlan

logger = logging.getLogger(__name__)


class ExplainMetricContextBuilder:
    def __init__(
        self,
        lightdash_client: LightdashClient,
        lightdash_search: LightdashSearchService,
        dbt_reader: DbtManifestReader,
        docs_searcher: PgFtsSearcher,
    ) -> None:
        self._lightdash_client = lightdash_client
        self._lightdash_search = lightdash_search
        self._dbt = dbt_reader
        self._docs = docs_searcher

    async def build_context(
        self,
        plan: ExplainMetricPlan,
        run: Run,
    ) -> ContextPack:
        (
            lightdash_metric_sources,
            dbt_metric_sources,
            kpi_glossary_sources,
            business_logic_sources,
            related_dashboard_sources,
        ) = await asyncio.gather(
            self._get_lightdash_metric(plan.normalized_metric_name),
            self._get_dbt_metric(plan.normalized_metric_name),
            self._get_docs(plan.metric_name, DocType.KPI_GLOSSARY),
            self._get_docs(plan.metric_name, DocType.BUSINESS_LOGIC),
            self._get_related_dashboards(plan.metric_name),
            return_exceptions=True,
        )

        all_sources: list[ContextSource] = []
        for result in (
            lightdash_metric_sources,
            dbt_metric_sources,
            kpi_glossary_sources,
            business_logic_sources,
            related_dashboard_sources,
        ):
            if isinstance(result, Exception):
                logger.warning("Context retrieval subtask failed: %s", result)
                continue
            all_sources.extend(result)

        # Deduplicate by object_ref (keep first seen)
        seen_refs: set[str] = set()
        deduped: list[ContextSource] = []
        for source in all_sources:
            if source.object_ref not in seen_refs:
                seen_refs.add(source.object_ref)
                deduped.append(source)

        unresolved: list[str] = []
        if len(deduped) == 0:
            unresolved.append(
                f"Metric '{plan.metric_name}' could not be found in any authoritative source."
            )

        logger.info(
            "Built context pack for run_id=%s: %d sources, %d unresolved ambiguities",
            run.run_id,
            len(deduped),
            len(unresolved),
        )

        return ContextPack(
            run_id=run.run_id,
            plan_id=plan.plan_id,
            skill_name=plan.skill_name,
            sources=deduped,
            unresolved_ambiguities=unresolved,
        )

    async def _get_lightdash_metric(self, normalized_metric_name: str) -> list[ContextSource]:
        metric = await self._lightdash_client.get_metric(normalized_metric_name)
        if metric is None:
            return []
        snippet = f"{metric.label}: {metric.description or ''}"
        return [
            ContextSource(
                source_type=SourceType.LIGHTDASH_METRIC,
                authority=SourceAuthority.PRIMARY,
                freshness="current",
                object_ref=metric.name,
                label=metric.label,
                snippet=snippet,
                metadata={
                    "table": metric.table,
                    "type": metric.type,
                    "tags": metric.tags,
                    "url": metric.url,
                },
            )
        ]

    async def _get_dbt_metric(self, normalized_metric_name: str) -> list[ContextSource]:
        metric = self._dbt.get_metric(normalized_metric_name)
        if metric is None:
            return []
        return self._dbt.metrics_to_context_sources([metric])

    async def _get_docs(self, metric_name: str, doc_type: DocType) -> list[ContextSource]:
        results = await self._docs.search(metric_name, doc_type=doc_type)
        return await self._docs.to_context_sources(results)

    async def _get_related_dashboards(self, metric_name: str) -> list[ContextSource]:
        sources = await self._lightdash_search.find_relevant_context(
            metric_name, max_results=5
        )
        # Keep only dashboard-type results for related dashboards context
        return [
            s for s in sources
            if s.source_type in (
                SourceType.LIGHTDASH_DASHBOARD,
                SourceType.LIGHTDASH_CHART,
            )
        ]
