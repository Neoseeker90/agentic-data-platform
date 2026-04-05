from __future__ import annotations

import httpx

from .exceptions import (
    LightdashAuthError,
    LightdashConnectionError,
    LightdashNotFoundError,
)
from .models import (
    ExploreDetail,
    ExploreField,
    LightdashDashboard,
    LightdashMetric,
    LightdashSearchResult,
    LightdashSpace,
    QueryResult,
)


class LightdashClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        project_uuid: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._project_uuid = project_uuid
        self._owns_client = http_client is None
        if http_client is None:
            self._client = httpx.AsyncClient(
                base_url=base_url,
                headers={"Authorization": f"ApiKey {api_key}"},
                timeout=httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0),
            )
        else:
            self._client = http_client

    async def _get(self, url: str) -> dict:
        try:
            response = await self._client.get(url)
        except httpx.RequestError as exc:
            raise LightdashConnectionError(str(exc)) from exc

        if response.status_code in (401, 403):
            raise LightdashAuthError(f"Authentication failed ({response.status_code}): {url}")
        if response.status_code == 404:
            raise LightdashNotFoundError(f"Resource not found: {url}")

        response.raise_for_status()
        return response.json()

    async def _post(self, url: str, body: dict) -> dict:
        try:
            response = await self._client.post(url, json=body)
        except httpx.RequestError as exc:
            raise LightdashConnectionError(str(exc)) from exc
        if response.status_code in (401, 403):
            raise LightdashAuthError(f"Authentication failed ({response.status_code}): {url}")
        if response.status_code == 404:
            raise LightdashNotFoundError(f"Resource not found: {url}")
        if not response.is_success:
            try:
                error_body = response.json()
                error_msg = error_body.get("error", {}).get("message", response.text)
            except Exception:
                error_msg = response.text
            raise LightdashConnectionError(
                f"POST {url} failed ({response.status_code}): {error_msg}"
            )
        return response.json()

    async def list_metrics(self) -> list[LightdashMetric]:
        """Fetch all metrics from all explores in the project."""
        data = await self._get(f"/api/v1/projects/{self._project_uuid}/explores")
        results: list[LightdashMetric] = []

        explores = data.get("results", [])
        for explore in explores:
            table_name = explore.get("name", "")
            metrics_raw = explore.get("metrics", [])
            for m in metrics_raw:
                results.append(
                    LightdashMetric(
                        metric_id=m.get("name", ""),
                        name=m.get("name", ""),
                        label=m.get("label", m.get("name", "")),
                        description=m.get("description"),
                        table=table_name,
                        type=m.get("type", ""),
                        tags=m.get("tags", []),
                        url=m.get("url"),
                    )
                )
        return results

    async def list_dashboards(self) -> list[LightdashDashboard]:
        """Fetch all dashboards in the project."""
        data = await self._get(f"/api/v1/projects/{self._project_uuid}/dashboards")
        results: list[LightdashDashboard] = []

        dashboards_raw = data.get("results", [])
        for d in dashboards_raw:
            results.append(
                LightdashDashboard(
                    dashboard_uuid=d.get("uuid", ""),
                    name=d.get("name", ""),
                    description=d.get("description"),
                    space_name=d.get("spaceName"),
                    url=d.get("url"),
                )
            )
        return results

    async def get_metric(self, metric_name: str) -> LightdashMetric | None:
        """Return the first metric matching metric_name, or None."""
        metrics = await self.list_metrics()
        for metric in metrics:
            if metric.name == metric_name:
                return metric
        return None

    async def get_dashboard(self, dashboard_uuid: str) -> LightdashDashboard | None:
        """Return a single dashboard by UUID, or None if not found."""
        try:
            data = await self._get(
                f"/api/v1/projects/{self._project_uuid}/dashboards/{dashboard_uuid}"
            )
        except LightdashNotFoundError:
            return None

        d = data.get("results", data)
        return LightdashDashboard(
            dashboard_uuid=d.get("uuid", dashboard_uuid),
            name=d.get("name", ""),
            description=d.get("description"),
            space_name=d.get("spaceName"),
            url=d.get("url"),
        )

    async def search(self, query: str) -> list[LightdashSearchResult]:
        """Search across metrics, dashboards, charts, and dimensions."""
        data = await self._get(f"/api/v1/projects/{self._project_uuid}/search/{query}")
        results: list[LightdashSearchResult] = []

        # Lightdash search returns { results: { dashboards: [], savedCharts: [],
        # spaces: [], tables: [], fields: [] } }
        raw = data.get("results", data)

        for item in raw.get("dashboards", []):
            results.append(
                LightdashSearchResult(
                    result_type="dashboard",
                    name=item.get("name", ""),
                    label=item.get("name", ""),
                    description=item.get("description"),
                    url=item.get("url"),
                    object_id=item.get("uuid", item.get("name", "")),
                )
            )

        for item in raw.get("savedCharts", []):
            results.append(
                LightdashSearchResult(
                    result_type="chart",
                    name=item.get("name", ""),
                    label=item.get("name", ""),
                    description=item.get("description"),
                    url=item.get("url"),
                    object_id=item.get("uuid", item.get("name", "")),
                )
            )

        for item in raw.get("fields", []):
            results.append(
                LightdashSearchResult(
                    result_type=item.get("fieldType", "metric"),
                    name=item.get("name", ""),
                    label=item.get("label", item.get("name", "")),
                    description=item.get("description"),
                    url=item.get("url"),
                    object_id=item.get("name", ""),
                )
            )

        for item in raw.get("tables", []):
            results.append(
                LightdashSearchResult(
                    result_type="table",
                    name=item.get("name", ""),
                    label=item.get("label", item.get("name", "")),
                    description=item.get("description"),
                    url=item.get("url"),
                    object_id=item.get("name", ""),
                )
            )

        return results

    async def list_explores(self) -> list[dict]:
        data = await self._get(f"/api/v1/projects/{self._project_uuid}/explores")
        return [
            {
                "name": e.get("name", ""),
                "label": e.get("label", ""),
                "description": e.get("description"),
            }
            for e in data.get("results", [])
        ]

    async def get_explore_detail(self, explore_name: str) -> ExploreDetail:

        data = await self._get(f"/api/v1/projects/{self._project_uuid}/explores/{explore_name}")
        results = data.get("results", {})
        tables = results.get("tables", {})
        label = results.get("label", explore_name)
        description = results.get("description")
        fields: list[ExploreField] = []
        for table_name, table in tables.items():
            for field_name, dim in table.get("dimensions", {}).items():
                fields.append(
                    ExploreField(
                        field_id=f"{table_name}_{field_name}",
                        label=dim.get("label", field_name),
                        description=dim.get("description"),
                        field_type="dimension",
                        type=dim.get("type", "string"),
                    )
                )
            for field_name, metric in table.get("metrics", {}).items():
                fields.append(
                    ExploreField(
                        field_id=f"{table_name}_{field_name}",
                        label=metric.get("label", field_name),
                        description=metric.get("description"),
                        field_type="metric",
                        type=metric.get("type", "number"),
                    )
                )
        return ExploreDetail(
            explore_name=explore_name, label=label, description=description, fields=fields
        )

    async def run_query(
        self,
        explore_name: str,
        dimensions: list[str],
        metrics: list[str],
        filters: dict,
        sorts: list[dict],
        limit: int = 100,
    ) -> QueryResult:

        body = {
            "exploreName": explore_name,
            "dimensions": dimensions,
            "metrics": metrics,
            "filters": filters,
            "sorts": sorts,
            "limit": limit,
            "tableCalculations": [],
            "additionalMetrics": [],
        }
        data = await self._post(
            f"/api/v1/projects/{self._project_uuid}/explores/{explore_name}/runQuery", body
        )
        results = data.get("results", {})
        rows = results.get("rows", [])
        fields = results.get("fields", {})
        return QueryResult(rows=rows, fields=fields, row_count=len(rows))

    async def list_spaces(self) -> list[LightdashSpace]:

        data = await self._get(f"/api/v1/projects/{self._project_uuid}/spaces")
        spaces = []
        for s in data.get("results", []):
            spaces.append(
                LightdashSpace(
                    space_uuid=s.get("uuid", ""),
                    name=s.get("name", ""),
                    is_private=s.get("isPrivate", False),
                )
            )
        return spaces

    def build_explore_url(
        self,
        explore_name: str,
        dimensions: list[str],
        metrics: list[str],
    ) -> str:
        """Build a Lightdash Explore URL for the given explore and fields.

        Lightdash's SPA does not support pre-selecting fields via URL query params.
        Returns the plain explore table URL; field selection is shown in the chat
        response text alongside the link.
        """
        base = str(self._client.base_url).rstrip("/")
        return f"{base}/projects/{self._project_uuid}/tables/{explore_name}"

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
