from __future__ import annotations

from contracts.context_pack import ContextSource, SourceAuthority, SourceType

from .client import LightdashClient


class LightdashSearchService:
    def __init__(self, client: LightdashClient) -> None:
        self._client = client

    async def find_relevant_context(
        self, query: str, max_results: int = 10
    ) -> list[ContextSource]:
        raw_results = await self._client.search(query)
        context_sources: list[ContextSource] = []

        for item in raw_results[:max_results]:
            result_type = item.result_type.lower()

            if result_type in ("metric", "dimension"):
                authority = SourceAuthority.PRIMARY
                source_type = SourceType.LIGHTDASH_METRIC
            elif result_type == "dashboard":
                authority = SourceAuthority.SECONDARY
                source_type = SourceType.LIGHTDASH_DASHBOARD
            elif result_type == "chart":
                authority = SourceAuthority.SECONDARY
                source_type = SourceType.LIGHTDASH_CHART
            else:
                authority = SourceAuthority.SUPPORTING
                source_type = SourceType.LIGHTDASH_METRIC

            snippet = f"{item.label}: {item.description or ''}"

            context_sources.append(
                ContextSource(
                    source_type=source_type,
                    authority=authority,
                    freshness="current",
                    object_ref=item.name,
                    label=item.label,
                    snippet=snippet,
                    metadata={
                        "result_type": item.result_type,
                        "url": item.url,
                        "object_id": item.object_id,
                    },
                )
            )

        return context_sources
