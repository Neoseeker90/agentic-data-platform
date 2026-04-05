from __future__ import annotations

from datetime import UTC, datetime

import asyncpg

from contracts.context_pack import ContextSource, SourceAuthority, SourceType

from .models import BusinessDoc, BusinessDocResult, DocType


class PgFtsSearcher:
    def __init__(self, database_url: str) -> None:
        # asyncpg requires "postgresql://" not "postgresql+asyncpg://"
        self._database_url = database_url.replace("postgresql+asyncpg://", "postgresql://")

    async def search(
        self,
        query: str,
        doc_type: DocType | None = None,
        max_results: int = 10,
    ) -> list[BusinessDocResult]:
        conn = await asyncpg.connect(self._database_url)
        try:
            if doc_type is not None:
                sql = """
                    SELECT
                        doc_id, doc_type, title, content, owner, source_path,
                        updated_at, ts_rank(search_vector, q) AS rank
                    FROM business_docs, to_tsquery('english', $1) AS q
                    WHERE search_vector @@ q AND doc_type = $2
                    ORDER BY rank DESC
                    LIMIT $3
                """
                rows = await conn.fetch(sql, query, str(doc_type), max_results)
            else:
                sql = """
                    SELECT
                        doc_id, doc_type, title, content, owner, source_path,
                        updated_at, ts_rank(search_vector, q) AS rank
                    FROM business_docs, to_tsquery('english', $1) AS q
                    WHERE search_vector @@ q
                    ORDER BY rank DESC
                    LIMIT $2
                """
                rows = await conn.fetch(sql, query, max_results)

            results: list[BusinessDocResult] = []
            for rank_idx, row in enumerate(rows, start=1):
                updated_at = row["updated_at"] or datetime.now(UTC)
                doc = BusinessDoc(
                    doc_id=row["doc_id"],
                    doc_type=DocType(row["doc_type"]),
                    title=row["title"],
                    content=row["content"],
                    owner=row["owner"],
                    source_path=row["source_path"],
                    updated_at=updated_at,
                )
                snippet = row["content"][:200]
                results.append(
                    BusinessDocResult(
                        doc=doc,
                        relevance_rank=rank_idx,
                        snippet=snippet,
                    )
                )
            return results
        finally:
            await conn.close()

    async def to_context_sources(self, results: list[BusinessDocResult]) -> list[ContextSource]:
        context_sources: list[ContextSource] = []

        for result in results:
            doc_type = result.doc.doc_type

            if doc_type == DocType.KPI_GLOSSARY:
                source_type = SourceType.KPI_GLOSSARY
                authority = SourceAuthority.SECONDARY
            else:
                # business_logic and caveat both map to BUSINESS_DOC / SUPPORTING
                source_type = SourceType.BUSINESS_DOC
                authority = SourceAuthority.SUPPORTING

            context_sources.append(
                ContextSource(
                    source_type=source_type,
                    authority=authority,
                    freshness="current",
                    object_ref=str(result.doc.doc_id),
                    label=result.doc.title,
                    snippet=result.snippet,
                    metadata={
                        "doc_type": str(result.doc.doc_type),
                        "owner": result.doc.owner,
                        "source_path": result.doc.source_path,
                        "relevance_rank": result.relevance_rank,
                    },
                )
            )

        return context_sources
