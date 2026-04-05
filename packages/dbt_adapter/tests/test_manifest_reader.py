from __future__ import annotations

from pathlib import Path

import pytest

from contracts.context_pack import SourceType
from dbt_adapter.exceptions import ManifestNotFoundError
from dbt_adapter.manifest_reader import DbtManifestReader

FIXTURES_DIR = Path(__file__).parent / "fixtures"
MANIFEST_PATH = FIXTURES_DIR / "manifest.json"


@pytest.fixture()
def reader() -> DbtManifestReader:
    r = DbtManifestReader(MANIFEST_PATH)
    r.load()
    return r


def test_load_parses_models(reader: DbtManifestReader) -> None:
    model = reader.get_model("fct_revenue")
    assert model is not None
    assert model.name == "fct_revenue"
    assert model.description == "Revenue fact table"


def test_search_models_by_keyword(reader: DbtManifestReader) -> None:
    results = reader.search_models("revenue")
    names = [m.name for m in results]
    assert "fct_revenue" in names


def test_get_metric(reader: DbtManifestReader) -> None:
    metric = reader.get_metric("net_revenue")
    assert metric is not None
    assert metric.label == "Net Revenue"


def test_search_metrics(reader: DbtManifestReader) -> None:
    results = reader.search_metrics("revenue")
    names = [m.name for m in results]
    assert "net_revenue" in names


def test_get_exposures(reader: DbtManifestReader) -> None:
    exposures = reader.get_exposures()
    assert len(exposures) >= 1
    names = [e.name for e in exposures]
    assert "revenue_dashboard" in names


def test_to_context_sources(reader: DbtManifestReader) -> None:
    model = reader.get_model("fct_revenue")
    assert model is not None
    sources = reader.to_context_sources([model])
    assert len(sources) == 1
    assert sources[0].source_type == SourceType.DBT_MODEL
    assert sources[0].object_ref == "fct_revenue"


def test_manifest_not_found() -> None:
    reader = DbtManifestReader(Path("/nonexistent/path/manifest.json"))
    with pytest.raises(ManifestNotFoundError):
        reader.load()


def test_search_case_insensitive(reader: DbtManifestReader) -> None:
    results = reader.search_models("REVENUE")
    names = [m.name for m in results]
    assert "fct_revenue" in names
