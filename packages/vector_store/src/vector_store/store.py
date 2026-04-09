from __future__ import annotations

import json
import logging

import asyncpg
from pgvector.asyncpg import register_vector

from .models import ContentType, SearchResult

logger = logging.getLogger(__name__)


class VectorStore:
    def __init__(self, database_url: str) -> None:
        # asyncpg uses postgresql:// not postgresql+asyncpg://
        self._dsn = database_url.replace("postgresql+asyncpg://", "postgresql://")
        self._available: bool | None = None

    async def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            conn = await asyncpg.connect(self._dsn)
            try:
                await register_vector(conn)
                row = await conn.fetchval(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                    "WHERE table_name = 'semantic_embeddings')"
                )
                self._available = bool(row)
            finally:
                await conn.close()
        except Exception as exc:
            logger.warning("pgvector availability check failed: %s", exc)
            self._available = False
        return self._available

    async def upsert(
        self,
        content_type: ContentType,
        object_ref: str,
        label: str,
        content_text: str,
        content_hash: str,
        embedding: list[float],
        metadata: dict | None = None,
    ) -> None:
        conn = await asyncpg.connect(self._dsn)
        try:
            await register_vector(conn)
            await conn.execute(
                """
                INSERT INTO semantic_embeddings
                    (content_type, object_ref, label, content_text,
                     content_hash, embedding, metadata, indexed_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,now())
                ON CONFLICT (content_type, object_ref) DO UPDATE SET
                    label=EXCLUDED.label, content_text=EXCLUDED.content_text,
                    content_hash=EXCLUDED.content_hash, embedding=EXCLUDED.embedding,
                    metadata=EXCLUDED.metadata, indexed_at=now()
                """,
                str(content_type),
                object_ref,
                label,
                content_text,
                content_hash,
                embedding,
                json.dumps(metadata or {}),
            )
        finally:
            await conn.close()

    async def get_existing_hashes(self, content_type: ContentType) -> dict[str, str]:
        conn = await asyncpg.connect(self._dsn)
        try:
            rows = await conn.fetch(
                "SELECT object_ref, content_hash FROM semantic_embeddings WHERE content_type=$1",
                str(content_type),
            )
            return {r["object_ref"]: r["content_hash"] for r in rows}
        finally:
            await conn.close()

    async def delete_stale(self, content_type: ContentType, valid_refs: set[str]) -> int:
        if not valid_refs:
            return 0
        conn = await asyncpg.connect(self._dsn)
        try:
            result = await conn.execute(
                "DELETE FROM semantic_embeddings WHERE content_type=$1 AND NOT (object_ref=ANY($2::text[]))",
                str(content_type),
                list(valid_refs),
            )
            return int(result.split()[-1])
        finally:
            await conn.close()

    async def search(
        self,
        query_embedding: list[float],
        *,
        content_types: list[ContentType] | None = None,
        max_results: int = 10,
        min_similarity: float = 0.3,
    ) -> list[SearchResult]:
        conn = await asyncpg.connect(self._dsn)
        try:
            await register_vector(conn)
            if content_types:
                rows = await conn.fetch(
                    """SELECT content_type, object_ref, label, content_text, metadata,
                              1-(embedding<=>$1::vector) AS similarity
                       FROM semantic_embeddings
                       WHERE content_type=ANY($2::text[])
                       ORDER BY embedding<=>$1::vector LIMIT $3""",
                    query_embedding,
                    [str(ct) for ct in content_types],
                    max_results,
                )
            else:
                rows = await conn.fetch(
                    """SELECT content_type, object_ref, label, content_text, metadata,
                              1-(embedding<=>$1::vector) AS similarity
                       FROM semantic_embeddings
                       ORDER BY embedding<=>$1::vector LIMIT $2""",
                    query_embedding,
                    max_results,
                )
            results = []
            for row in rows:
                sim = float(row["similarity"])
                if sim < min_similarity:
                    continue
                meta = row["metadata"]
                if isinstance(meta, str):
                    meta = json.loads(meta)
                results.append(
                    SearchResult(
                        content_type=ContentType(row["content_type"]),
                        object_ref=row["object_ref"],
                        label=row["label"],
                        content_text=row["content_text"],
                        metadata=dict(meta) if meta else {},
                        similarity=sim,
                    )
                )
            return results
        finally:
            await conn.close()
