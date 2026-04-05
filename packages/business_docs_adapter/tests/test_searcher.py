from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from business_docs_adapter.indexer import BusinessDocsIndexer
from business_docs_adapter.models import BusinessDoc, BusinessDocResult, DocType
from business_docs_adapter.pg_fts import PgFtsSearcher
from contracts.context_pack import SourceType

FIXTURES_DIR = Path(__file__).parent / "fixtures"
DB_URL = "postgresql://test:test@localhost/testdb"


def make_mock_row(
    *,
    doc_type: str = "kpi_glossary",
    title: str = "Test Doc",
    content: str = "This is a test document with relevant content about KPIs.",
    owner: str | None = "finance",
) -> MagicMock:
    row = MagicMock()
    row.__getitem__ = MagicMock(
        side_effect=lambda key: {
            "doc_id": uuid4(),
            "doc_type": doc_type,
            "title": title,
            "content": content,
            "owner": owner,
            "source_path": None,
            "updated_at": None,
        }[key]
    )
    return row


@pytest.mark.asyncio
async def test_search_returns_business_doc_results() -> None:
    mock_row = make_mock_row()

    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[mock_row])
    mock_conn.close = AsyncMock()

    with patch("asyncpg.connect", return_value=mock_conn):
        searcher = PgFtsSearcher(DB_URL)
        results = await searcher.search("kpi")

    assert len(results) == 1
    assert isinstance(results[0], BusinessDocResult)
    assert results[0].relevance_rank == 1
    assert len(results[0].snippet) <= 200


@pytest.mark.asyncio
async def test_search_filters_by_doc_type() -> None:
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[])
    mock_conn.close = AsyncMock()

    with patch("asyncpg.connect", return_value=mock_conn):
        searcher = PgFtsSearcher(DB_URL)
        await searcher.search("revenue", doc_type=DocType.KPI_GLOSSARY)

    call_args = mock_conn.fetch.call_args
    # The SQL query string is the first positional argument
    sql_query: str = call_args[0][0]
    assert "doc_type" in sql_query
    # The doc_type value should be passed as a bind parameter
    assert "kpi_glossary" in call_args[0]


@pytest.mark.asyncio
async def test_to_context_sources_kpi_glossary() -> None:
    doc = BusinessDoc(
        doc_type=DocType.KPI_GLOSSARY,
        title="Active Customer",
        content="A customer who placed an order in the last 90 days.",
    )
    result = BusinessDocResult(doc=doc, relevance_rank=1, snippet=doc.content[:200])

    searcher = PgFtsSearcher(DB_URL)
    sources = await searcher.to_context_sources([result])

    assert len(sources) == 1
    assert sources[0].source_type == SourceType.KPI_GLOSSARY
    assert sources[0].authority.value == "secondary"


@pytest.mark.asyncio
async def test_to_context_sources_business_logic() -> None:
    doc = BusinessDoc(
        doc_type=DocType.BUSINESS_LOGIC,
        title="Revenue Calculation",
        content="Revenue is calculated by multiplying units sold by unit price.",
    )
    result = BusinessDocResult(doc=doc, relevance_rank=1, snippet=doc.content[:200])

    searcher = PgFtsSearcher(DB_URL)
    sources = await searcher.to_context_sources([result])

    assert len(sources) == 1
    assert sources[0].source_type == SourceType.BUSINESS_DOC
    assert sources[0].authority.value == "supporting"


@pytest.mark.asyncio
async def test_index_directory_parses_frontmatter() -> None:
    indexed_docs: list[BusinessDoc] = []

    async def capture_index(self_inner: BusinessDocsIndexer, doc: BusinessDoc) -> None:
        indexed_docs.append(doc)

    with patch.object(BusinessDocsIndexer, "index_document", capture_index):
        indexer = BusinessDocsIndexer(DB_URL)
        count = await indexer.index_directory(FIXTURES_DIR)

    assert count >= 1

    glossary_docs = [d for d in indexed_docs if d.doc_type == DocType.KPI_GLOSSARY]
    assert len(glossary_docs) >= 1

    glossary_doc = glossary_docs[0]
    assert glossary_doc.owner == "finance"
    assert glossary_doc.doc_type == DocType.KPI_GLOSSARY
