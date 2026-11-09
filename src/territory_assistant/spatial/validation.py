"""Contrôles CRS et géométries, choix du CRS métrique."""

from __future__ import annotations

import geopandas as gpd
import shapely
from pyproj import CRS
from pyproj.exceptions import CRSError as PyprojCRSError
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
)
from shapely.geometry.base import BaseGeometry

from territory_assistant.errors import CRSError

_DIM = {
    "Point": 0,
    "MultiPoint": 0,
    "LineString": 1,
    "MultiLineString": 1,
    "LinearRing": 1,
    "Polygon": 2,
    "MultiPolygon": 2,
}


def crs_label(crs: CRS | None) -> str:
    """Libellé lisible et stable d'un CRS (ex. « EPSG:2154 »)."""
    if crs is None:
        return "absent"
    auth = crs.to_authority()
    return f"{auth[0]}:{auth[1]}" if auth else crs.name


def require_crs(gdf: gpd.GeoDataFrame, label: str) -> CRS:
    """Refuse une couche sans CRS : aucune hypothèse silencieuse n'est faite."""
    if gdf.crs is None:
        raise CRSError(
            f"{label} : système de coordonnées absent. Déclarer le CRS dans le fichier "
            "(ou le convertir) avant l'analyse ; aucune hypothèse n'est faite."
        )
    return CRS.from_user_input(gdf.crs)


def check_coordinates_plausible(gdf: gpd.GeoDataFrame, label: str) -> None:
    """Détecte un CRS manifestement erroné (ex. coordonnées métriques déclarées en degrés)."""
    if gdf.empty or gdf.geometry.isna().all():
        return
    crs = CRS.from_user_input(gdf.crs)
    minx, miny, maxx, maxy = gdf.geometry.dropna().total_bounds
    if crs.is_geographic and (minx < -180 or maxx > 180 or miny < -90 or maxy > 90):
        raise CRSError(
            f"{label} : coordonnées hors des bornes géographiques alors que le CRS déclaré "
            f"({crs_label(crs)}) est en degrés. Le CRS déclaré est probablement erroné."
        )


def is_metric_projected(crs: CRS) -> bool:
    if not crs.is_projected:
        return False
    units = {(ax.unit_name or "").lower() for ax in crs.axis_info}
    return bool(units) and units <= {"metre", "meter", "m"}


def choose_metric_crs(
    area_wgs84: gpd.GeoDataFrame, configured: str | None
) -> tuple[CRS, list[str]]:
    """Retourne le CRS utilisé pour les mesures et les avertissements associés.

    - CRS imposé : doit être projeté et en mètres ; on vérifie que la zone est dans
      son domaine de validité.
    - Sinon : zone UTM estimée par GeoPandas à partir de l'emprise de la zone.
    """
    warnings: list[str] = []
    if configured:
        try:
            crs = CRS.from_user_input(configured)
        except PyprojCRSError as exc:
            raise CRSError(f"CRS métrique configuré inconnu : {configured}") from exc
        if not is_metric_projected(crs):
            raise CRSError(
                f"CRS métrique configuré inadapté aux mesures (non projeté ou non métrique) : {configured}"
            )
    else:
        crs = area_wgs84.estimate_utm_crs()
        warnings.append(
            f"CRS de calcul choisi automatiquement : {crs_label(crs)} ({crs.name}). "
            "Pour une étude réelle, préférer le CRS de référence du territoire."
        )
    aou = crs.area_of_use
    if aou is not None:
        minx, miny, maxx, maxy = area_wgs84.total_bounds
        if minx < aou.west or maxx > aou.east or miny < aou.south or maxy > aou.north:
            warnings.append(
                f"La zone d'étude dépasse le domaine de validité de {crs_label(crs)} "
                f"({aou.name}) : déformations possibles des mesures."
            )
    return crs, warnings


def _keep_dimension(geom: BaseGeometry, dim: int) -> BaseGeometry:
    """Après make_valid, conserve uniquement les parties de la dimension d'origine."""
    if geom.is_empty or _DIM.get(geom.geom_type) == dim:
        return geom
    parts = []
    stack = [geom]
    while stack:
        g = stack.pop()
        if isinstance(g, GeometryCollection | MultiPolygon | MultiLineString | MultiPoint):
            stack.extend(g.geoms)
        elif _DIM.get(g.geom_type) == dim:
            parts.append(g)
    if not parts:
        return GeometryCollection()
    if dim == 2:
        return MultiPolygon(
            [
                p
                for g in parts
                for p in (g.geoms if isinstance(g, MultiPolygon) else [g])
                if isinstance(p, Polygon)
            ]
        )
    if dim == 1:
        return MultiLineString(
            [
                p
                for g in parts
                for p in (g.geoms if isinstance(g, MultiLineString) else [g])
                if isinstance(p, LineString)
            ]
        )
    return MultiPoint(
        [
            p
            for g in parts
            for p in (g.geoms if isinstance(g, MultiPoint) else [g])
            if isinstance(p, Point)
        ]
    )


def repair_geometries(
    gdf: gpd.GeoDataFrame, label: str, id_column: str | None = None
) -> tuple[gpd.GeoDataFrame, int, int, list[str]]:
    """Supprime les géométries vides et répare les invalides (shapely.make_valid).

    Retourne (couche nettoyée, nb réparées, nb vides supprimées, avertissements).
    Chaque réparation est signalée avec la raison GEOS et l'identifiant de l'entité.
    """
    warnings: list[str] = []

    def _ident(idx) -> str:
        if id_column and id_column in gdf.columns:
            return str(gdf.at[idx, id_column])
        return f"index {idx}"

    empty_mask = gdf.geometry.isna() | gdf.geometry.is_empty
    n_empty = int(empty_mask.sum())
    if n_empty:
        ids = ", ".join(_ident(i) for i in gdf.index[empty_mask])
        warnings.append(f"{label} : {n_empty} géométrie(s) vide(s) ignorée(s) ({ids}).")
    out = gdf.loc[~empty_mask].copy()

    invalid_mask = ~out.geometry.is_valid
    n_fixed = 0
    if invalid_mask.any():
        for idx in out.index[invalid_mask]:
            geom = out.at[idx, out.geometry.name]
            reason = shapely.is_valid_reason(geom)
            dim = _DIM.get(geom.geom_type, 2)
            fixed = _keep_dimension(shapely.make_valid(geom), dim)
            out.at[idx, out.geometry.name] = fixed
            n_fixed += 1
            warnings.append(
                f"{label} : géométrie invalide réparée par make_valid ({_ident(idx)} — {reason}). "
                "La réparation automatique peut modifier la forme : à contrôler."
            )
        still_empty = out.geometry.is_empty
        if still_empty.any():
            warnings.append(
                f"{label} : {int(still_empty.sum())} géométrie(s) vide(s) après réparation, ignorée(s)."
            )
            out = out.loc[~still_empty]
    return out, n_fixed, n_empty, warnings


def geometry_family(geom_type: str) -> str:
    dim = _DIM.get(geom_type)
    return {0: "point", 1: "line", 2: "polygon"}.get(dim, "mixed")
