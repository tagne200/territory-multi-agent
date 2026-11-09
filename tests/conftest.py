"""Fixtures communes : chemins du jeu d'exemple et fabriques de petits fichiers SIG."""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import box

from territory_assistant.config import Settings
from territory_assistant.models import AnalysisRequest

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "sample"
QUESTION = "Quels éléments territoriaux doivent être examinés avant une étude d'aménagement dans cette zone ?"

# Repère en Lambert-93 (EPSG:2154), coordonnées arbitraires : géométries de test exactes en mètres.
X0, Y0 = 650_000.0, 6_860_000.0


@pytest.fixture
def settings() -> Settings:
    return Settings()  # mode sans LLM, valeurs par défaut


@pytest.fixture
def sample_request() -> AnalysisRequest:
    return AnalysisRequest(
        question=QUESTION,
        project_type="aménagement",
        study_area_path=SAMPLE / "study_area.geojson",
        layer_paths=sorted((SAMPLE / "layers").glob("*.geojson"))
        + sorted((SAMPLE / "layers").glob("*.gpkg")),
        document_paths=sorted(
            p for p in (SAMPLE / "documents").iterdir() if not p.name.endswith(".meta.json")
        ),
        allowed_roots=[ROOT],
    )


def square(size: float = 1000.0, dx: float = 0.0, dy: float = 0.0):
    return box(X0 + dx, Y0 + dy, X0 + dx + size, Y0 + dy + size)


def write_layer(path: Path, geoms, crs="EPSG:2154", meta: dict | None = None, **cols) -> Path:
    gdf = gpd.GeoDataFrame(
        cols or {"id": [f"E{i}" for i in range(len(geoms))]}, geometry=list(geoms), crs=crs
    )
    driver = "GPKG" if path.suffix == ".gpkg" else "GeoJSON"
    gdf.to_file(path, driver=driver)
    if meta is not None:
        path.with_name(f"{path.stem}.meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return path
