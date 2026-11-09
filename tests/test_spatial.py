"""Tests SIG : intersections, CRS, géométries, couches vides, attributs."""

from __future__ import annotations

import geopandas as gpd
import pytest
from pyproj import CRS
from shapely.geometry import LineString, Point, Polygon

from territory_assistant.errors import CRSError, DataReadError, GeometryError
from territory_assistant.models import SidecarMetadata
from territory_assistant.spatial.analysis import analyze_layer, prepare_layer, prepare_study_area
from territory_assistant.spatial.loader import read_vector
from territory_assistant.spatial.validation import choose_metric_crs, repair_geometries

from .conftest import X0, Y0, square, write_layer


def _area(gdf, metric="EPSG:2154"):
    return prepare_study_area(
        gdf, source_id="area:t", name="t", metric_crs_setting=metric, max_area_km2=100
    )


def _layer(gdf, metric_crs, meta=None):
    return prepare_layer(
        gdf,
        layer_id="L01",
        source_id="layer:t",
        filename="t",
        meta=meta or SidecarMetadata(name="t", theme="hydrography", id_attribute="id"),
        metric_crs=metric_crs,
        read_warnings=[],
    )


def test_expected_intersection_known_geometry():
    area = gpd.GeoDataFrame(geometry=[square(1000)], crs="EPSG:2154")
    sa, geom, crs, _ = _area(area)
    assert sa.area_m2 == pytest.approx(1_000_000, rel=1e-9)
    line = LineString(
        [(X0 - 500, Y0 + 500), (X0 + 1500, Y0 + 500)]
    )  # traverse : 1000 m dans la zone
    layer = gpd.GeoDataFrame({"id": ["R1"]}, geometry=[line], crs="EPSG:2154")
    lgdf, lm = _layer(layer, crs)
    f = analyze_layer(lgdf, lm, area_geom=geom, area_m2=sa.area_m2, buffer_m=0, id_prefix="F")
    assert len(f) == 1 and f[0].relation == "intersects" and f[0].feature_id == "R1"
    length = next(m for m in f[0].metrics if m.name == "longueur_dans_zone")
    assert length.value == pytest.approx(1000.0, abs=0.1)
    assert length.unit == "m" and length.crs == "EPSG:2154"
    assert f[0].source_id == "layer:t" and "aucune" in f[0].crs_transformation


def test_polygon_share_of_zone():
    area = gpd.GeoDataFrame(geometry=[square(1000)], crs="EPSG:2154")
    sa, geom, crs, _ = _area(area)
    poly = gpd.GeoDataFrame(
        {"id": ["V1"]}, geometry=[square(500, dx=-250)], crs="EPSG:2154"
    )  # 250 x 500 dans la zone
    lgdf, lm = _layer(poly, crs)
    f = analyze_layer(lgdf, lm, area_geom=geom, area_m2=sa.area_m2, buffer_m=0, id_prefix="F")[0]
    vals = {m.name: m.value for m in f.metrics}
    assert vals["surface_dans_zone"] == pytest.approx(125_000, abs=1)
    assert vals["part_de_la_zone"] == pytest.approx(12.5, abs=0.01)
    assert vals["part_de_l_entite_dans_zone"] == pytest.approx(50.0, abs=0.01)


def test_no_intersection_and_buffer():
    area = gpd.GeoDataFrame(geometry=[square(1000)], crs="EPSG:2154")
    sa, geom, crs, _ = _area(area)
    far = gpd.GeoDataFrame(
        {"id": ["A", "B"]}, geometry=[square(100, dx=1100), square(100, dx=5000)], crs="EPSG:2154"
    )
    lgdf, lm = _layer(far, crs)
    assert (
        analyze_layer(lgdf, lm, area_geom=geom, area_m2=sa.area_m2, buffer_m=0, id_prefix="F") == []
    )
    near = analyze_layer(lgdf, lm, area_geom=geom, area_m2=sa.area_m2, buffer_m=200, id_prefix="F")
    assert [(x.feature_id, x.relation, x.distance_m) for x in near] == [
        ("A", "within_buffer", 100.0)
    ]


def test_touching_boundary_is_not_an_intersection_with_area():
    area = gpd.GeoDataFrame(geometry=[square(1000)], crs="EPSG:2154")
    sa, geom, crs, _ = _area(area)
    touching = gpd.GeoDataFrame({"id": ["T"]}, geometry=[square(100, dx=1000)], crs="EPSG:2154")
    lgdf, lm = _layer(touching, crs)
    f = analyze_layer(lgdf, lm, area_geom=geom, area_m2=sa.area_m2, buffer_m=0, id_prefix="F")
    assert f[0].relation == "touches_boundary" and f[0].metrics == []


def test_invalid_geometry_is_repaired_with_warning():
    bowtie = Polygon([(X0, Y0), (X0 + 100, Y0 + 100), (X0 + 100, Y0), (X0, Y0 + 100), (X0, Y0)])
    gdf = gpd.GeoDataFrame({"id": ["B"]}, geometry=[bowtie], crs="EPSG:2154")
    assert not gdf.is_valid.iloc[0]
    out, n_fixed, n_empty, warnings = repair_geometries(gdf, "test", "id")
    assert n_fixed == 1 and n_empty == 0 and out.is_valid.all()
    assert out.geom_type.iloc[0] in {"Polygon", "MultiPolygon"}
    assert any("make_valid" in w and "B" in w for w in warnings)


def test_empty_geometry_removed():
    gdf = gpd.GeoDataFrame({"id": ["A", "B"]}, geometry=[square(10), None], crs="EPSG:2154")
    out, _, n_empty, warnings = repair_geometries(gdf, "test", "id")
    assert len(out) == 1 and n_empty == 1 and "B" in warnings[0]


@pytest.mark.filterwarnings("ignore:'crs' was not provided")
def test_missing_crs_is_refused(tmp_path):
    path = write_layer(tmp_path / "sans_crs.gpkg", [square(100)], crs=None)
    gdf, _ = read_vector(path, max_features=100)
    assert gdf.crs is None
    with pytest.raises(CRSError, match="absent"):
        _layer(gdf, CRS.from_epsg(2154))
    with pytest.raises(CRSError):
        _area(gdf)


def test_implausible_coordinates_for_geographic_crs():
    gdf = gpd.GeoDataFrame(geometry=[square(100)], crs="EPSG:4326")  # mètres déclarés en degrés
    with pytest.raises(CRSError, match="probablement erroné"):
        _area(gdf)


def test_reprojection_before_area_computation():
    """Zone fournie en degrés : la surface doit être calculée après reprojection métrique."""
    area_l93 = gpd.GeoDataFrame(geometry=[square(1000)], crs="EPSG:2154")
    area_wgs = area_l93.to_crs("EPSG:4326")
    sa, geom, crs, warnings = _area(area_wgs, metric=None)  # UTM automatique
    assert sa.crs_original == "EPSG:4326" and crs.is_projected
    assert sa.crs_metric.startswith("EPSG:326")
    # même surface qu'en Lambert-93, à la déformation des projections près (< 0,5 %)
    assert sa.area_m2 == pytest.approx(1_000_000, rel=5e-3)
    with pytest.warns(UserWarning, match="geographic CRS"):
        assert area_wgs.geometry.area.iloc[0] < 1  # en degrés, la "surface" serait absurde
    assert any("automatiquement" in w for w in warnings)


def test_layer_reprojected_to_metric_crs():
    sa, geom, crs, _ = _area(gpd.GeoDataFrame(geometry=[square(1000)], crs="EPSG:2154"))
    layer = gpd.GeoDataFrame(
        {"id": ["R"]},
        geometry=[LineString([(X0 - 10, Y0 + 500), (X0 + 1010, Y0 + 500)])],
        crs="EPSG:2154",
    ).to_crs("EPSG:4326")
    lgdf, lm = _layer(layer, crs)
    assert lm.reprojected and lm.crs_original == "EPSG:4326" and lm.crs_metric == "EPSG:2154"
    f = analyze_layer(lgdf, lm, area_geom=geom, area_m2=sa.area_m2, buffer_m=0, id_prefix="F")[0]
    assert "EPSG:4326 → EPSG:2154" in f.crs_transformation
    assert f.metrics[0].value == pytest.approx(1000, abs=0.5)


def test_geographic_crs_refused_for_measurements():
    area = gpd.GeoDataFrame(geometry=[square(1000)], crs="EPSG:2154").to_crs("EPSG:4326")
    with pytest.raises(CRSError, match="non projeté"):
        choose_metric_crs(area, "EPSG:4326")


def test_empty_layer():
    sa, geom, crs, _ = _area(gpd.GeoDataFrame(geometry=[square(1000)], crs="EPSG:2154"))
    empty = gpd.GeoDataFrame({"id": []}, geometry=[], crs="EPSG:2154")
    lgdf, lm = _layer(empty, crs)
    assert lm.feature_count_total == 0 and any("vide" in w for w in lm.warnings)
    assert (
        analyze_layer(lgdf, lm, area_geom=geom, area_m2=sa.area_m2, buffer_m=200, id_prefix="F")
        == []
    )


def test_missing_attributes_reported():
    _, _, crs, _ = _area(gpd.GeoDataFrame(geometry=[square(1000)], crs="EPSG:2154"))
    gdf = gpd.GeoDataFrame(
        {"id": ["A", "B"], "nom": ["x", None]},
        geometry=[square(10), square(10, dx=20)],
        crs="EPSG:2154",
    )
    meta = SidecarMetadata(
        name="t",
        theme="other",
        id_attribute="id",
        label_attribute="nom",
        expected_attributes=["nom", "regime"],
    )
    _, lm = _layer(gdf, crs, meta)
    assert lm.missing_attributes == {"nom": 1, "regime": 2}


def test_missing_id_attribute_falls_back_to_index():
    sa, geom, crs, _ = _area(gpd.GeoDataFrame(geometry=[square(1000)], crs="EPSG:2154"))
    gdf = gpd.GeoDataFrame({"autre": [1]}, geometry=[Point(X0 + 5, Y0 + 5)], crs="EPSG:2154")
    lgdf, lm = _layer(gdf, crs, SidecarMetadata(name="p", id_attribute="id"))
    assert any("absent" in w for w in lm.warnings)
    f = analyze_layer(lgdf, lm, area_geom=geom, area_m2=sa.area_m2, buffer_m=0, id_prefix="F")[0]
    assert f.feature_id == "index 0" and f.metrics[0].name == "nombre_de_points_dans_zone"


def test_study_area_must_be_polygonal():
    lines = gpd.GeoDataFrame(geometry=[LineString([(X0, Y0), (X0 + 10, Y0)])], crs="EPSG:2154")
    with pytest.raises(GeometryError, match="surfacique"):
        _area(lines)


def test_study_area_too_large():
    big = gpd.GeoDataFrame(geometry=[square(20_000)], crs="EPSG:2154")  # 400 km²
    with pytest.raises(GeometryError, match="trop grande"):
        _area(big)


def test_geojson_without_crs_member_warns(tmp_path):
    p = tmp_path / "sans_membre_crs.geojson"
    p.write_text(
        '{"type":"FeatureCollection","features":[{"type":"Feature","properties":{},'
        '"geometry":{"type":"Point","coordinates":[2.0,48.0]}}]}',
        encoding="utf-8",
    )
    gdf, warnings = read_vector(p, max_features=10)
    assert gdf.crs is not None and gdf.crs.to_epsg() == 4326
    assert any("RFC 7946" in w for w in warnings)


def test_corrupted_file_raises_read_error(tmp_path):
    p = tmp_path / "casse.geojson"
    p.write_text('{"type": "FeatureCollection", "features": [', encoding="utf-8")
    with pytest.raises(DataReadError, match="malformé"):
        read_vector(p, max_features=10)
    q = tmp_path / "faux.gpkg"
    q.write_bytes(b"ceci n'est pas un geopackage")
    with pytest.raises(DataReadError):
        read_vector(q, max_features=10)


def test_feature_limit(tmp_path):
    p = write_layer(tmp_path / "beaucoup.gpkg", [square(1, dx=i * 2) for i in range(20)])
    with pytest.raises(DataReadError, match="limite"):
        read_vector(p, max_features=10)


def test_gpkg_with_several_layers_requires_layer_name(tmp_path):
    p = tmp_path / "multi.gpkg"
    gpd.GeoDataFrame({"id": ["a"]}, geometry=[square(10)], crs="EPSG:2154").to_file(
        p, layer="a", driver="GPKG"
    )
    gpd.GeoDataFrame({"id": ["b"]}, geometry=[square(10)], crs="EPSG:2154").to_file(
        p, layer="b", driver="GPKG"
    )
    with pytest.raises(DataReadError, match="plusieurs couches"):
        read_vector(p, max_features=10)
    gdf, _ = read_vector(p, max_features=10, gpkg_layer="b")
    assert list(gdf["id"]) == ["b"]
