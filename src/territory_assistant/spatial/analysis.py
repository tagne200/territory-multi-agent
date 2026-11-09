"""Calculs spatiaux déterministes : préparation de la zone, intersections, mesures.

Règles :
- aucune surface ni longueur n'est calculée dans un CRS géographique (degrés) ;
- toutes les mesures sont faites dans un CRS projeté métrique unique ;
- une intersection est un constat géométrique, jamais une conclusion réglementaire.
"""

from __future__ import annotations

import json
import math
from datetime import date

import geopandas as gpd
import pandas as pd
from pyproj import CRS
from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry

from territory_assistant.errors import CRSError, GeometryError
from territory_assistant.models import (
    LayerMetadata,
    Metric,
    SidecarMetadata,
    SpatialFinding,
    StudyArea,
)
from territory_assistant.spatial.validation import (
    check_coordinates_plausible,
    choose_metric_crs,
    crs_label,
    geometry_family,
    is_metric_projected,
    repair_geometries,
    require_crs,
)

_MAX_ATTR_LEN = 200


def json_safe(value):
    """Convertit une valeur d'attribut en scalaire JSON (NaN -> None, dates -> ISO)."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, pd.Timestamp | date):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):  # types numpy
        return json_safe(value.item())
    return str(value)[:_MAX_ATTR_LEN]


# --------------------------------------------------------------------------- zone d'étude


def prepare_study_area(
    gdf: gpd.GeoDataFrame,
    *,
    source_id: str,
    name: str,
    metric_crs_setting: str | None,
    max_area_km2: float,
) -> tuple[StudyArea, BaseGeometry, CRS, list[str]]:
    """Valide la zone d'étude et retourne (StudyArea, géométrie métrique, CRS métrique, avertissements)."""
    label = "Zone d'étude"
    crs_orig = require_crs(gdf, label)
    check_coordinates_plausible(gdf, label)
    gdf, n_fixed, n_empty, warnings = repair_geometries(gdf, label)
    if gdf.empty:
        raise GeometryError("Zone d'étude vide : aucune géométrie exploitable.")
    families = {geometry_family(t) for t in gdf.geom_type}
    if families != {"polygon"}:
        raise GeometryError(
            f"La zone d'étude doit être surfacique (Polygon/MultiPolygon) ; types trouvés : "
            f"{', '.join(sorted(set(gdf.geom_type)))}."
        )
    n_input = len(gdf)
    if n_input > 1:
        warnings.append(
            f"Zone d'étude composée de {n_input} entités : elles ont été fusionnées (union)."
        )

    wgs84 = gdf.to_crs("EPSG:4326")
    metric_crs, crs_warnings = choose_metric_crs(wgs84, metric_crs_setting)
    warnings.extend(crs_warnings)

    geom_metric = gdf.to_crs(metric_crs).geometry.union_all()
    if geom_metric.is_empty or geom_metric.area <= 0:
        raise GeometryError("Zone d'étude de surface nulle.")
    area_m2 = float(geom_metric.area)
    if area_m2 / 1e6 > max_area_km2:
        raise GeometryError(
            f"Zone d'étude trop grande pour ce prototype ({area_m2 / 1e6:.1f} km² > {max_area_km2:.0f} km²)."
        )
    geom_wgs = wgs84.geometry.union_all()
    c = geom_wgs.centroid  # centroïde indicatif (affichage seulement)
    minx, miny, maxx, maxy = geom_wgs.bounds
    study = StudyArea(
        source_id=source_id,
        name=name,
        crs_original=crs_label(crs_orig),
        crs_metric=crs_label(metric_crs),
        area_m2=round(area_m2, 1),
        area_ha=round(area_m2 / 10_000, 2),
        bbox_wgs84=(round(minx, 6), round(miny, 6), round(maxx, 6), round(maxy, 6)),
        centroid_wgs84=(round(c.x, 6), round(c.y, 6)),
        n_input_features=n_input,
        # aller-retour JSON : tuples -> listes, pour un rapport identique une fois relu
        geometry_wgs84=json.loads(json.dumps(mapping(geom_wgs))),
        warnings=warnings,
    )
    return study, geom_metric, metric_crs, warnings


# --------------------------------------------------------------------------- couches


def prepare_layer(
    gdf: gpd.GeoDataFrame,
    *,
    layer_id: str,
    source_id: str,
    filename: str,
    meta: SidecarMetadata | None,
    metric_crs: CRS,
    read_warnings: list[str],
) -> tuple[gpd.GeoDataFrame, LayerMetadata]:
    """Contrôle CRS + géométries d'une couche et la reprojette dans le CRS métrique."""
    m = meta or SidecarMetadata()
    name = m.name or filename
    label = f"Couche « {name} »"
    warnings = list(read_warnings)

    crs_orig = require_crs(gdf, label)
    check_coordinates_plausible(gdf, label)
    total = len(gdf)
    id_col = m.id_attribute if m.id_attribute in gdf.columns else None
    if m.id_attribute and not id_col:
        warnings.append(
            f"{label} : attribut identifiant « {m.id_attribute} » absent ; index utilisé."
        )
    elif not m.id_attribute:
        warnings.append(f"{label} : aucun attribut identifiant déclaré ; index de ligne utilisé.")

    cleaned, n_fixed, n_empty, geom_warnings = repair_geometries(gdf, label, id_col)
    warnings.extend(geom_warnings)
    if total == 0:
        warnings.append(f"{label} : couche vide (0 entité).")

    reprojected = CRS.from_user_input(crs_orig) != metric_crs
    metric = cleaned.to_crs(metric_crs) if reprojected else cleaned
    if not is_metric_projected(CRS.from_user_input(metric.crs)):
        raise CRSError(f"{label} : CRS de calcul non métrique, mesures refusées.")

    attributes = [c for c in gdf.columns if c != gdf.geometry.name]
    missing: dict[str, int] = {}
    for attr in m.expected_attributes:
        if attr not in gdf.columns:
            missing[attr] = total
            warnings.append(f"{label} : attribut attendu « {attr} » absent de la couche.")
        else:
            n_null = int(gdf[attr].isna().sum())
            if n_null:
                missing[attr] = n_null
                warnings.append(
                    f"{label} : attribut « {attr} » non renseigné pour {n_null} entité(s)."
                )

    lm = LayerMetadata(
        layer_id=layer_id,
        source_id=source_id,
        name=name,
        theme=m.theme or "other",
        filename=filename,
        description=m.description or "non renseignée",
        load_status="ok",
        geometry_types=sorted(set(cleaned.geom_type)) if not cleaned.empty else [],
        feature_count_total=total,
        feature_count_used=len(metric),
        crs_original=crs_label(crs_orig),
        crs_metric=crs_label(metric_crs),
        reprojected=reprojected,
        invalid_geometries_fixed=n_fixed,
        empty_geometries_removed=n_empty,
        attributes=attributes,
        missing_attributes=missing,
        id_attribute=id_col,
        label_attribute=m.label_attribute if m.label_attribute in gdf.columns else None,
        scale_denominator=m.scale_denominator,
        date=m.date or "non renseignée",
        status=m.status or "non renseignée",
        warnings=warnings,
    )
    return metric, lm


def _pct(part: float, whole: float) -> float:
    return round(100.0 * part / whole, 2) if whole > 0 else 0.0


def analyze_layer(
    layer: gpd.GeoDataFrame,
    lm: LayerMetadata,
    *,
    area_geom: BaseGeometry,
    area_m2: float,
    buffer_m: float,
    id_prefix: str,
) -> list[SpatialFinding]:
    """Détecte les entités qui intersectent la zone (ou sont à moins de `buffer_m`).

    Toutes les géométries sont supposées dans le même CRS métrique (vérifié en amont).
    """
    if layer.empty:
        return []
    crs = lm.crs_metric
    transfo = (
        f"{lm.crs_original} → {crs} (GeoPandas.to_crs / PyProj)"
        if lm.reprojected
        else f"aucune (couche déjà en {crs})"
    )
    search_geom = area_geom.buffer(buffer_m) if buffer_m > 0 else area_geom
    candidates = layer[layer.geometry.intersects(search_geom)]

    findings: list[SpatialFinding] = []
    geom_col = layer.geometry.name
    for n, (idx, row) in enumerate(candidates.iterrows(), start=1):
        geom: BaseGeometry = row[geom_col]
        fam = geometry_family(geom.geom_type)
        attrs = {k: json_safe(v) for k, v in row.items() if k != geom_col}
        fid = str(attrs.get(lm.id_attribute)) if lm.id_attribute else f"index {idx}"
        label = attrs.get(lm.label_attribute) if lm.label_attribute else None
        warnings: list[str] = []
        if lm.label_attribute and label is None:
            warnings.append(f"Attribut « {lm.label_attribute} » non renseigné pour cette entité.")

        metrics: list[Metric] = []
        distance = None
        params: dict = {"buffer_m": buffer_m, "crs_calcul": crs}
        if geom.intersects(area_geom):
            inter = geom.intersection(area_geom)
            if fam == "polygon":
                a = float(inter.area)
                relation = "intersects" if a > 0.01 else "touches_boundary"
                op = "intersection(entité, zone) puis aire (m²)"
                if relation == "intersects":
                    metrics = [
                        Metric(name="surface_dans_zone", value=round(a, 1), unit="m²", crs=crs),
                        Metric(
                            name="surface_dans_zone_ha",
                            value=round(a / 10_000, 2),
                            unit="ha",
                            crs=crs,
                        ),
                        Metric(name="part_de_la_zone", value=_pct(a, area_m2), unit="%", crs=crs),
                        Metric(
                            name="part_de_l_entite_dans_zone",
                            value=_pct(a, float(geom.area)),
                            unit="%",
                            crs=crs,
                        ),
                    ]
            elif fam == "line":
                length = float(inter.length)
                relation = "intersects" if length > 0.01 else "touches_boundary"
                op = "intersection(entité, zone) puis longueur (m)"
                if relation == "intersects":
                    metrics = [
                        Metric(
                            name="longueur_dans_zone", value=round(length, 1), unit="m", crs=crs
                        ),
                        Metric(
                            name="part_de_l_entite_dans_zone",
                            value=_pct(length, float(geom.length)),
                            unit="%",
                            crs=crs,
                        ),
                    ]
            else:
                relation = "intersects"
                op = "test d'inclusion du point dans la zone"
                n_pts = len(getattr(inter, "geoms", [inter])) if not inter.is_empty else 0
                metrics = [
                    Metric(
                        name="nombre_de_points_dans_zone",
                        value=float(n_pts),
                        unit="entité(s)",
                        crs=crs,
                    )
                ]
            if relation == "touches_boundary":
                warnings.append(
                    "Contact limité à la limite de la zone (aucune longueur/surface commune)."
                )
        else:
            relation = "within_buffer"
            distance = round(float(geom.distance(area_geom)), 1)
            op = f"distance minimale à la zone (m), tampon de recherche {buffer_m:g} m"
            metrics = [Metric(name="distance_a_la_zone", value=distance, unit="m", crs=crs)]

        findings.append(
            SpatialFinding(
                finding_id=f"{id_prefix}-{n:03d}",
                layer_id=lm.layer_id,
                source_id=lm.source_id,
                layer_name=lm.name,
                theme=lm.theme,
                feature_id=fid,
                feature_label=None if label is None else str(label),
                attributes=attrs,
                relation=relation,  # type: ignore[arg-type]
                geometry_type=geom.geom_type,
                metrics=metrics,
                distance_m=distance,
                operation=op,
                parameters=params,
                crs_transformation=transfo,
                warnings=warnings,
            )
        )
    return findings


def findings_to_geodataframe(
    layers: dict[str, gpd.GeoDataFrame],
    findings: list[SpatialFinding],
    area_geom: BaseGeometry,
    metric_crs: CRS,
    id_columns: dict[str, str | None],
) -> gpd.GeoDataFrame:
    """Géométries des constats (partie dans la zone, ou entité entière si proximité), en WGS84."""
    rows = []
    for f in findings:
        layer = layers.get(f.layer_id)
        if layer is None:
            continue
        col = id_columns.get(f.layer_id)
        if col:
            sel = layer[layer[col].astype(str) == f.feature_id]
        else:
            sel = layer.loc[[int(f.feature_id.split()[-1])]]
        if sel.empty:
            continue
        g = sel.geometry.iloc[0]
        geom = g.intersection(area_geom) if f.relation == "intersects" else g
        rows.append(
            {
                "finding_id": f.finding_id,
                "source_id": f.source_id,
                "layer": f.layer_name,
                "feature_id": f.feature_id,
                "relation": f.relation,
                "geometry": geom,
            }
        )
    if not rows:
        return gpd.GeoDataFrame(
            {"finding_id": [], "source_id": [], "layer": [], "feature_id": [], "relation": []},
            geometry=[],
            crs=metric_crs,
        ).to_crs("EPSG:4326")
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=metric_crs).to_crs("EPSG:4326")
