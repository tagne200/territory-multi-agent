"""Lecture des fichiers vectoriels (GeoJSON, GeoPackage) avec garde-fous."""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pyogrio

from territory_assistant.errors import DataReadError


def _geojson_declares_crs(path: Path) -> bool:
    """Indique si un GeoJSON contient un membre « crs » (ancienne spécification 2008).

    Lève DataReadError si le fichier n'est pas un JSON valide.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DataReadError(f"GeoJSON malformé ({path.name}) : {exc}") from exc
    if not isinstance(data, dict) or data.get("type") not in {
        "FeatureCollection",
        "Feature",
        "Polygon",
        "MultiPolygon",
        "LineString",
        "MultiLineString",
        "Point",
        "MultiPoint",
        "GeometryCollection",
    }:
        raise DataReadError(f"Le fichier {path.name} n'est pas un objet GeoJSON reconnu.")
    return "crs" in data


def read_vector(
    path: Path, *, max_features: int, gpkg_layer: str | None = None
) -> tuple[gpd.GeoDataFrame, list[str]]:
    """Lit un fichier vectoriel et retourne (GeoDataFrame, avertissements).

    - GeoJSON : selon la RFC 7946, un fichier sans membre « crs » est en WGS84
      (EPSG:4326) ; on le signale explicitement.
    - GeoPackage : si plusieurs couches existent, le nom de couche doit être fourni
      (champ `gpkg_layer` des métadonnées).
    - Le nombre d'entités est contrôlé AVANT lecture complète.
    """
    warnings: list[str] = []
    ext = path.suffix.lower()
    layer = None

    if ext in {".geojson", ".json"} and not _geojson_declares_crs(path):
        warnings.append(
            f"{path.name} : aucun membre « crs » ; CRS WGS84 (EPSG:4326) supposé conformément à la RFC 7946."
        )

    try:
        if ext == ".gpkg":
            layers = [row[0] for row in pyogrio.list_layers(path)]
            if not layers:
                raise DataReadError(f"Aucune couche dans le GeoPackage {path.name}.")
            if gpkg_layer:
                if gpkg_layer not in layers:
                    raise DataReadError(
                        f"Couche « {gpkg_layer} » absente de {path.name} (couches : {', '.join(layers)})."
                    )
                layer = gpkg_layer
            elif len(layers) > 1:
                raise DataReadError(
                    f"{path.name} contient plusieurs couches ({', '.join(layers)}) : "
                    "préciser « gpkg_layer » dans le fichier de métadonnées."
                )
            else:
                layer = layers[0]
        info = pyogrio.read_info(path, layer=layer)
        n = int(info.get("features", -1))
        if n > max_features:
            raise DataReadError(f"{path.name} contient {n} entités (> limite de {max_features}).")
        gdf = gpd.read_file(path, engine="pyogrio", layer=layer)
    except DataReadError:
        raise
    except Exception as exc:  # erreurs GDAL/pyogrio hétérogènes -> message unique
        raise DataReadError(
            f"Lecture impossible de {path.name} : {type(exc).__name__}: {exc}"
        ) from exc

    if not isinstance(gdf, gpd.GeoDataFrame) or gdf.geometry.name not in gdf.columns:
        raise DataReadError(f"{path.name} ne contient pas de colonne géométrique.")
    return gdf, warnings
