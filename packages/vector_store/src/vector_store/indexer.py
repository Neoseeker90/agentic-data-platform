from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .embedder import BedrockEmbedder
from .models import ContentType, EmbeddingRecord
from .store import VectorStore

if TYPE_CHECKING:
    from dbt_adapter.manifest_reader import DbtManifestReader
    from lightdash_adapter.client import LightdashClient

logger = logging.getLogger(__name__)


class SemanticIndexer:
    def __init__(
        self,
        embedder: BedrockEmbedder,
        store: VectorStore,
        dbt_reader: DbtManifestReader,
        lightdash_client: LightdashClient | None = None,
    ) -> None:
        self._embedder = embedder
        self._store = store
        self._dbt = dbt_reader
        self._lightdash = lightdash_client

    async def run_full_index(self) -> dict[str, int]:
        if not await self._store.is_available():
            logger.warning("pgvector not available — skipping semantic indexing")
            return {}
        stats: dict[str, int] = {}
        for name, coro in [
            ("dbt_metrics", self._index_dbt_metrics()),
            ("dbt_models", self._index_dbt_models()),
            ("lightdash", self._index_lightdash()),
        ]:
            try:
                stats[name] = await coro
            except Exception as exc:
                logger.error("Indexing %s failed: %s", name, exc)
                stats[name] = 0
        total = sum(stats.values())
        logger.info("Semantic indexing complete: %d items. %s", total, stats)
        return stats

    async def _index_dbt_metrics(self) -> int:
        records = [
            EmbeddingRecord(
                content_type=ContentType.DBT_METRIC,
                object_ref=m.name,
                label=m.label or m.name,
                content_text=self._text(m.name, m.label, m.description),
                metadata={"unique_id": m.unique_id, "type": m.type},
            )
            for m in self._dbt._metrics.values()
        ]
        return await self._upsert(ContentType.DBT_METRIC, records)

    async def _index_dbt_models(self) -> int:
        # Only index models that are exposed in Lightdash explores.
        # Indexing all 1000+ dbt models (staging, raw, intermediate) would flood
        # search results with irrelevant infrastructure models.
        expose_names: list[str] = []
        if self._lightdash is not None:
            try:
                explores = await self._lightdash.list_explores()
                expose_names = [e["name"] for e in explores]
            except Exception as exc:
                logger.warning("Could not fetch explores for model filtering: %s", exc)

        models_to_index = (
            [m for m in self._dbt._models.values() if m.name in expose_names]
            if expose_names
            else list(self._dbt._models.values())
        )

        records = [
            EmbeddingRecord(
                content_type=ContentType.DBT_MODEL,
                object_ref=m.name,
                label=m.name,
                content_text=self._text(m.name, None, m.description),
                metadata={"unique_id": m.unique_id, "tags": m.tags},
            )
            for m in models_to_index
        ]
        return await self._upsert(ContentType.DBT_MODEL, records)

    async def _index_lightdash(self) -> int:
        if not self._lightdash:
            return 0
        records: list[EmbeddingRecord] = []
        try:
            dashboards = await self._lightdash.list_dashboards()
            for d in dashboards:
                records.append(
                    EmbeddingRecord(
                        content_type=ContentType.LIGHTDASH_DASHBOARD,
                        object_ref=d.dashboard_uuid,
                        label=d.name,
                        content_text=self._text(d.name, None, d.description),
                        metadata={"url": d.url},
                    )
                )
        except Exception as exc:
            logger.warning("Failed to fetch dashboards for indexing: %s", exc)
        try:
            explores = await self._lightdash.list_explores()
            for e in explores:
                try:
                    detail = await self._lightdash.get_explore_detail(e["name"])
                    for f in detail.fields:
                        records.append(
                            EmbeddingRecord(
                                content_type=ContentType.LIGHTDASH_FIELD,
                                object_ref=f.field_id,
                                label=f.label,
                                content_text=self._text(f.field_id, f.label, f.description),
                                metadata={"explore": e["name"], "field_type": f.field_type},
                            )
                        )
                except Exception as exc:
                    logger.warning("Failed to get explore detail for %s: %s", e["name"], exc)
        except Exception as exc:
            logger.warning("Failed to list explores for indexing: %s", exc)

        # Index by content_type grouping
        by_type: dict[ContentType, list[EmbeddingRecord]] = {}
        for r in records:
            by_type.setdefault(r.content_type, []).append(r)
        total = 0
        for ct, recs in by_type.items():
            total += await self._upsert(ct, recs)
        return total

    async def _upsert(self, ct: ContentType, records: list[EmbeddingRecord]) -> int:
        if not records:
            return 0
        existing = await self._store.get_existing_hashes(ct)
        to_embed = [
            r
            for r in records
            if existing.get(r.object_ref) != BedrockEmbedder.content_hash(r.content_text)
        ]
        if not to_embed:
            logger.info("No changes for %s (%d up to date)", ct, len(records))
        else:
            logger.info("Embedding %d/%d %s records", len(to_embed), len(records), ct)
            embeddings = await self._embedder.embed_batch([r.content_text for r in to_embed])
            for rec, emb in zip(to_embed, embeddings, strict=False):
                try:
                    await self._store.upsert(
                        content_type=rec.content_type,
                        object_ref=rec.object_ref,
                        label=rec.label,
                        content_text=rec.content_text,
                        content_hash=BedrockEmbedder.content_hash(rec.content_text),
                        embedding=emb,
                        metadata=rec.metadata,
                    )
                except Exception as exc:
                    logger.warning("Failed to upsert %s/%s: %s", ct, rec.object_ref, exc)
        valid = {r.object_ref for r in records}
        deleted = await self._store.delete_stale(ct, valid)
        if deleted:
            logger.info("Deleted %d stale %s embeddings", deleted, ct)
        return len(to_embed)

    @staticmethod
    def _text(name: str, label: str | None, description: str | None) -> str:
        parts = [name]
        if label and label != name:
            parts.append(label)
        if description:
            parts.append(description)
        return " | ".join(parts)
