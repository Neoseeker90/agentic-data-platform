from __future__ import annotations

import logging

from contracts.context_pack import ContextSource, SourceAuthority, SourceType

from .embedder import BedrockEmbedder
from .models import ContentType, SearchResult
from .store import VectorStore

logger = logging.getLogger(__name__)

_TYPE_MAP: dict[ContentType, tuple[SourceType, SourceAuthority]] = {
    ContentType.DBT_METRIC: (SourceType.DBT_METRIC, SourceAuthority.PRIMARY),
    ContentType.DBT_MODEL: (SourceType.DBT_MODEL, SourceAuthority.PRIMARY),
    ContentType.LIGHTDASH_DASHBOARD: (SourceType.LIGHTDASH_DASHBOARD, SourceAuthority.SECONDARY),
    ContentType.LIGHTDASH_CHART: (SourceType.LIGHTDASH_CHART, SourceAuthority.SECONDARY),
    ContentType.LIGHTDASH_FIELD: (SourceType.LIGHTDASH_METRIC, SourceAuthority.PRIMARY),
}


class SemanticSearchService:
    def __init__(self, embedder: BedrockEmbedder, store: VectorStore) -> None:
        self._embedder = embedder
        self._store = store

    async def is_available(self) -> bool:
        return await self._store.is_available()

    async def search(
        self,
        query: str,
        *,
        content_types: list[ContentType] | None = None,
        max_results: int = 10,
        min_similarity: float = 0.3,
    ) -> list[ContextSource]:
        try:
            query_embedding = await self._embedder.embed_text(query)
            results = await self._store.search(
                query_embedding,
                content_types=content_types,
                max_results=max_results,
                min_similarity=min_similarity,
            )
            return [self._to_context_source(r) for r in results]
        except Exception as exc:
            logger.warning("Semantic search failed (falling back to keyword): %s", exc)
            return []

    def _to_context_source(self, r: SearchResult) -> ContextSource:
        source_type, authority = _TYPE_MAP.get(
            r.content_type, (SourceType.LIGHTDASH_METRIC, SourceAuthority.SUPPORTING)
        )
        meta = dict(r.metadata)
        meta["similarity"] = r.similarity
        return ContextSource(
            source_type=source_type,
            authority=authority,
            freshness="current",
            object_ref=r.object_ref,
            label=r.label,
            snippet=r.content_text,
            metadata=meta,
        )
