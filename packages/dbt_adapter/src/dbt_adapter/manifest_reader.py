from __future__ import annotations

import json
from pathlib import Path

from contracts.context_pack import ContextSource, SourceAuthority, SourceType

from .exceptions import ManifestNotFoundError, ManifestParseError
from .models import DbtColumn, DbtExposure, DbtMetric, DbtModel, DbtSource


class DbtManifestReader:
    def __init__(self, manifest_path: Path) -> None:
        self._manifest_path = manifest_path
        self._models: dict[str, DbtModel] = {}
        self._metrics: dict[str, DbtMetric] = {}
        self._exposures: list[DbtExposure] = []
        self._sources: list[DbtSource] = []

    def load(self) -> None:
        """Parse manifest.json and populate internal data structures.

        Raises:
            ManifestNotFoundError: if the manifest file does not exist.
            ManifestParseError: if the file is not valid JSON or has unexpected structure.
        """
        if not self._manifest_path.exists():
            raise ManifestNotFoundError(f"manifest.json not found at: {self._manifest_path}")

        try:
            raw = json.loads(self._manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ManifestParseError(f"Invalid JSON in manifest: {exc}") from exc

        try:
            self._parse_nodes(raw.get("nodes", {}))
            self._parse_metrics(raw.get("metrics", {}))
            self._parse_exposures(raw.get("exposures", {}))
            self._parse_sources(raw.get("sources", {}))
        except (KeyError, TypeError, ValueError) as exc:
            raise ManifestParseError(f"Unexpected manifest structure: {exc}") from exc

    def _parse_nodes(self, nodes: dict) -> None:
        for unique_id, node in nodes.items():
            resource_type = node.get("resource_type", "")
            if resource_type != "model":
                continue

            columns_raw = node.get("columns", {})
            columns = {
                col_name: DbtColumn(
                    name=col_data.get("name", col_name) if isinstance(col_data, dict) else col_name,
                    description=col_data.get("description") if isinstance(col_data, dict) else None,
                    data_type=col_data.get("data_type") if isinstance(col_data, dict) else None,
                )
                for col_name, col_data in columns_raw.items()
            }

            depends_on = node.get("depends_on", {}).get("nodes", [])

            model = DbtModel(
                unique_id=unique_id,
                name=node["name"],
                description=node.get("description"),
                schema_name=node.get("schema"),
                tags=node.get("tags", []),
                columns=columns,
                raw_sql=node.get("raw_code") or node.get("raw_sql"),
                depends_on=depends_on,
            )
            self._models[node["name"].lower()] = model

    def _parse_metrics(self, metrics: dict) -> None:
        for unique_id, m in metrics.items():
            depends_on = m.get("depends_on", {}).get("nodes", [])
            metric = DbtMetric(
                unique_id=unique_id,
                name=m["name"],
                label=m.get("label"),
                description=m.get("description"),
                type=m.get("type", "simple"),
                expression=m.get("expression"),
                depends_on=depends_on,
            )
            self._metrics[m["name"].lower()] = metric

    def _parse_exposures(self, exposures: dict) -> None:
        self._exposures = []
        for unique_id, e in exposures.items():
            depends_on = e.get("depends_on", {}).get("nodes", [])
            exposure = DbtExposure(
                unique_id=unique_id,
                name=e["name"],
                description=e.get("description"),
                type=e.get("type", ""),
                depends_on=depends_on,
                url=e.get("url"),
            )
            self._exposures.append(exposure)

    def _parse_sources(self, sources: dict) -> None:
        self._sources = []
        for unique_id, s in sources.items():
            source = DbtSource(
                unique_id=unique_id,
                name=s["name"],
                schema_name=s.get("schema"),
                description=s.get("description"),
                tables=[t["name"] for t in s.get("tables", [])],
            )
            self._sources.append(source)

    def get_model(self, model_name: str) -> DbtModel | None:
        return self._models.get(model_name.lower())

    def search_models(self, query: str) -> list[DbtModel]:
        query_lower = query.lower()
        matches: list[DbtModel] = []

        for model in self._models.values():
            searchable = " ".join([model.name, model.description or ""] + model.tags).lower()
            if query_lower in searchable:
                matches.append(model)

        return sorted(matches, key=lambda m: len(m.name))[:10]

    def get_metric(self, metric_name: str) -> DbtMetric | None:
        return self._metrics.get(metric_name.lower())

    def search_metrics(self, query: str) -> list[DbtMetric]:
        query_lower = query.lower()
        matches: list[DbtMetric] = []

        for metric in self._metrics.values():
            searchable = " ".join(
                [metric.name, metric.description or "", metric.label or ""]
            ).lower()
            if query_lower in searchable:
                matches.append(metric)

        return matches

    def get_exposures(self) -> list[DbtExposure]:
        return list(self._exposures)

    def get_sources(self) -> list[DbtSource]:
        return list(self._sources)

    def to_context_sources(self, models: list[DbtModel]) -> list[ContextSource]:
        return [
            ContextSource(
                source_type=SourceType.DBT_MODEL,
                authority=SourceAuthority.PRIMARY,
                freshness="current",
                object_ref=model.name,
                label=model.name,
                snippet=model.description or model.name,
                metadata={
                    "unique_id": model.unique_id,
                    "schema": model.schema_name,
                    "tags": model.tags,
                },
            )
            for model in models
        ]

    def metrics_to_context_sources(self, metrics: list[DbtMetric]) -> list[ContextSource]:
        return [
            ContextSource(
                source_type=SourceType.DBT_METRIC,
                authority=SourceAuthority.PRIMARY,
                freshness="current",
                object_ref=metric.name,
                label=metric.label or metric.name,
                snippet=metric.description or metric.name,
                metadata={
                    "unique_id": metric.unique_id,
                    "type": metric.type,
                    "expression": metric.expression,
                },
            )
            for metric in metrics
        ]
