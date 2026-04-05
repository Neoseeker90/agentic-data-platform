from __future__ import annotations

import re
import subprocess
from datetime import date, timezone, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml


_BASE_DIR_NAME = "agent_content"  # {dbt_project}/agent_content/charts/ & /dashboards/


class ChartUploader:
    """Generate Lightdash chart/dashboard YAML files and upload via the CLI.

    The Lightdash CLI expects files organised as:
        {base_path}/charts/*.yml
        {base_path}/dashboards/*.yml
    and is invoked with ``lightdash upload -p {base_path}``.
    """

    def __init__(
        self,
        lightdash_url: str,
        project_uuid: str,
        dbt_project_path: str,
        api_key: str = "",
    ) -> None:
        self.lightdash_url = lightdash_url.rstrip("/")
        self.project_uuid = project_uuid
        self._api_key = api_key
        # Base path that contains charts/ and dashboards/ subdirs
        self._base_path = Path(dbt_project_path) / _BASE_DIR_NAME

    def _make_slug(self, title: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40]
        return f"{base}-{date.today().strftime('%Y%m%d')}"

    def _chart_yaml(self, plan: Any, slug: str, chart_type: str = "bar") -> dict:
        dimensions = plan.dimensions

        # Pick xField: prefer date-type dimension, otherwise last dimension
        x_field = dimensions[-1] if dimensions else (plan.metrics[0] if plan.metrics else "")
        for d in dimensions:
            if any(t in d for t in ["_date", "_month", "_week", "_year", "_quarter", "_day"]):
                x_field = d
                break

        # Pivot dims are group-by columns (all non-x dimensions).
        # In Lightdash, pivot is declared at chart top level via pivotConfig,
        # NOT inside the series. The series encode only references x + y fields.
        pivot_dims = [d for d in dimensions if d != x_field]

        # Use list() copies so PyYAML doesn't emit YAML anchors when the same
        # list object appears in both metricQuery.metrics and chartConfig.yField.
        metrics_copy = list(plan.metrics)

        series = [
            {
                "type": chart_type,
                "encode": {
                    "xRef": {"field": x_field},
                    "yRef": {"field": metric},
                },
            }
            for metric in metrics_copy
        ]

        if chart_type == "table":
            chart_config: dict = {"type": "table", "config": {}}
        else:
            chart_config = {
                "type": "cartesian",
                "config": {
                    "layout": {"xField": x_field, "yField": list(metrics_copy)},
                    "eChartsConfig": {"series": series},
                },
            }

        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        data: dict = {
            "name": plan.chart_title or plan.intent_summary or "Agent Chart",
            "description": plan.intent_summary or "",
            "updatedAt": now_iso,
            "tableName": plan.explore_name,
            "metricQuery": {
                "exploreName": plan.explore_name,
                "dimensions": list(plan.dimensions),
                "metrics": list(metrics_copy),
                "filters": {
                    "metrics": {"id": "chart_metric_filters", "and": []},
                    "dimensions": {"id": "chart_dimension_filters", "and": []},
                    "tableCalculations": {"id": "chart_tc_filters", "and": []},
                },
                "sorts": list(plan.sorts),
                "limit": min(plan.limit, 500),
                "metricOverrides": {},
                "dimensionOverrides": {},
                "tableCalculations": [],
                "additionalMetrics": [],
            },
            "chartConfig": chart_config,
            "slug": slug,
            "tableConfig": {"columnOrder": list(plan.dimensions) + list(metrics_copy)},
            "spaceSlug": "agent-answers",
            "version": 1,
        }

        # pivotConfig: top-level Lightdash field for group-by dimensions
        if pivot_dims:
            data["pivotConfig"] = {"columns": list(pivot_dims)}

        return data

    def _dashboard_yaml(
        self,
        chart_slug: str,
        chart_name: str,
        dashboard_title: str,
        slug: str,
    ) -> dict:
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        return {
            "name": dashboard_title,
            "description": f"Auto-generated dashboard — {chart_name}",
            "updatedAt": now_iso,
            "tiles": [{
                "x": 0,
                "y": 0,
                "h": 9,
                "w": 36,
                "tabUuid": None,
                "type": "saved_chart",
                "properties": {
                    "title": "",
                    "hideTitle": False,
                    "chartSlug": chart_slug,
                    "chartName": chart_name,
                },
                "tileSlug": chart_slug,
            }],
            "filters": {"metrics": [], "dimensions": [], "tableCalculations": []},
            "tabs": [],
            "slug": slug,
            "spaceSlug": "agent-answers",
            "version": 1,
        }

    def _get_dashboard_uuid(self, name: str) -> str | None:
        """Fetch dashboards from the API and find the UUID matching the given name."""
        try:
            r = httpx.get(
                f"{self.lightdash_url}/api/v1/projects/{self.project_uuid}/dashboards",
                headers={"Authorization": f"ApiKey {self._api_key}"},
                timeout=10,
            )
            for d in r.json().get("results", []):
                if d.get("name") == name:
                    return d.get("uuid")
        except Exception:
            pass
        return None

    def _run_upload(self) -> None:
        """Run ``lightdash upload -p {base_path} --include-charts --force``."""
        result = subprocess.run(
            [
                "lightdash", "upload",
                "--project", self.project_uuid,
                "--force",
                "-p", str(self._base_path),
                "--include-charts",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"lightdash upload failed (exit {result.returncode}):\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )

    def upload_chart(self, plan: Any) -> tuple[str, str]:
        """Write chart YAML into {base}/charts/ and upload.

        Returns (chart_slug, chart_url).
        """
        title = plan.chart_title or plan.intent_summary or "agent-chart"
        slug = self._make_slug(title)

        charts_dir = self._base_path / "charts"
        charts_dir.mkdir(parents=True, exist_ok=True)

        yaml_path = charts_dir / f"{slug}.yml"
        with open(yaml_path, "w") as f:
            yaml.dump(
                self._chart_yaml(plan, slug),
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )

        self._run_upload()

        chart_url = f"{self.lightdash_url}/projects/{self.project_uuid}/charts/{slug}"
        return slug, chart_url

    def upload_dashboard_with_chart(self, plan: Any) -> tuple[str, str]:
        """Write chart + dashboard YAMLs and upload both.

        Returns (dashboard_slug, dashboard_url).
        """
        title = plan.chart_title or plan.intent_summary or "agent-chart"
        chart_slug = self._make_slug(title)
        chart_name = plan.chart_title or title

        # Write chart YAML
        charts_dir = self._base_path / "charts"
        charts_dir.mkdir(parents=True, exist_ok=True)
        with open(charts_dir / f"{chart_slug}.yml", "w") as f:
            yaml.dump(
                self._chart_yaml(plan, chart_slug),
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )

        # Write dashboard YAML
        dash_title = plan.chart_title or title
        dash_slug = self._make_slug(f"{dash_title}-dashboard")
        dashboards_dir = self._base_path / "dashboards"
        dashboards_dir.mkdir(parents=True, exist_ok=True)
        with open(dashboards_dir / f"{dash_slug}.yml", "w") as f:
            yaml.dump(
                self._dashboard_yaml(chart_slug, chart_name, dash_title, dash_slug),
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )

        self._run_upload()

        # Resolve UUID — Lightdash dashboard URLs use UUID, not slug
        dashboard_name = plan.chart_title or title
        dash_uuid = self._get_dashboard_uuid(dashboard_name)
        if dash_uuid:
            dashboard_url = (
                f"{self.lightdash_url}/projects/{self.project_uuid}"
                f"/dashboards/{dash_uuid}/view"
            )
        else:
            # Fallback: use slug (won't resolve but better than nothing)
            dashboard_url = (
                f"{self.lightdash_url}/projects/{self.project_uuid}"
                f"/dashboards/{dash_slug}/view"
            )
        return dash_slug, dashboard_url
