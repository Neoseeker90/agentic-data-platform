from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from contracts.context_pack import ContextSource, SourceType
from lightdash_adapter.client import LightdashClient
from lightdash_adapter.exceptions import LightdashAuthError, LightdashNotFoundError
from lightdash_adapter.search import LightdashSearchService

FIXTURES_DIR = Path(__file__).parent / "fixtures"
BASE_URL = "https://lightdash.example.com"
PROJECT_UUID = "test-project-uuid"
SEARCH_URL = f"{BASE_URL}/api/v1/projects/{PROJECT_UUID}/search/revenue"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


def make_client(http_client: httpx.AsyncClient) -> LightdashClient:
    return LightdashClient(
        base_url=BASE_URL,
        api_key="test-api-key",
        project_uuid=PROJECT_UUID,
        http_client=http_client,
    )


@pytest.mark.asyncio
@respx.mock
async def test_search_returns_context_sources() -> None:
    fixture = load_fixture("metric_list.json")
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(200, json=fixture))

    async with httpx.AsyncClient(base_url=BASE_URL) as http:
        client = make_client(http)
        results = await client.search("revenue")

    assert len(results) == 4  # 1 dashboard + 1 chart + 2 fields
    names = [r.name for r in results]
    assert "Total Revenue" in names  # field label
    assert "Revenue Overview" in names  # dashboard name


@pytest.mark.asyncio
@respx.mock
async def test_auth_error_raises() -> None:
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(401, json={"message": "Unauthorized"}))

    async with httpx.AsyncClient(base_url=BASE_URL) as http:
        client = make_client(http)
        with pytest.raises(LightdashAuthError):
            await client.search("revenue")


@pytest.mark.asyncio
@respx.mock
async def test_not_found_raises() -> None:
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(404, json={"message": "Not found"}))

    async with httpx.AsyncClient(base_url=BASE_URL) as http:
        client = make_client(http)
        with pytest.raises(LightdashNotFoundError):
            await client.search("revenue")


@pytest.mark.asyncio
@respx.mock
async def test_search_service_maps_to_context_sources() -> None:
    fixture = load_fixture("metric_list.json")
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(200, json=fixture))

    async with httpx.AsyncClient(base_url=BASE_URL) as http:
        client = make_client(http)
        service = LightdashSearchService(client)
        sources = await service.find_relevant_context("revenue")

    assert all(isinstance(s, ContextSource) for s in sources)

    source_types = {s.source_type for s in sources}
    assert SourceType.LIGHTDASH_METRIC in source_types
    assert SourceType.LIGHTDASH_DASHBOARD in source_types

    metric_sources = [s for s in sources if s.source_type == SourceType.LIGHTDASH_METRIC]
    dashboard_sources = [s for s in sources if s.source_type == SourceType.LIGHTDASH_DASHBOARD]

    assert len(metric_sources) == 2
    assert len(dashboard_sources) == 1

    for s in metric_sources:
        assert s.freshness == "current"
        assert s.authority.value == "primary"

    for s in dashboard_sources:
        assert s.authority.value == "secondary"
