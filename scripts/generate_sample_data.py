"""Génère le jeu de données FICTIF de démonstration (reproductible, sans téléchargement).

Toutes les géométries sont définies en mètres dans un repère local centré sur un point
situé EN MER (golfe de Gascogne, lon -5.0, lat 46.5), puis converties dans le CRS de
chaque fichier. Ce choix garantit qu'aucune limite fictive ne peut être confondue avec
un territoire réel. Les valeurs attendues (longueurs, surfaces) sont analytiques et
documentées dans docs/data_sources.md et evaluation/cases/.

Usage :
    python scripts/generate_sample_data.py
"""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
from pyproj import CRS, Transformer
from shapely import segmentize
from shapely.affinity import translate
from shapely.geometry import LineString, Polygon, box

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "sample"
LAYERS = SAMPLE / "layers"

LOCAL_CRS = CRS.from_epsg(32630)  # UTM 30N, repère de conception (mètres)
CENTER_LON, CENTER_LAT = -5.0, 46.5
_to_utm = Transformer.from_crs("EPSG:4326", LOCAL_CRS, always_xy=True)
E0, N0 = _to_utm.transform(CENTER_LON, CENTER_LAT)

FICTIF = "Données FICTIVES générées par scripts/generate_sample_data.py — aucune valeur réelle"
LICENCE = "CC0-1.0 (données fictives créées pour ce prototype)"


def place(geom, densify: bool = True):
    """Repère local (m, centré) -> UTM 30N, avec densification (25 m) pour limiter
    les écarts lors des reprojections.

    `densify=False` pour la géométrie volontairement invalide : la densification
    insérerait un sommet au point de croisement et GEOS la considérerait valide.
    """
    moved = translate(geom, E0, N0)
    return segmentize(moved, 25.0) if densify else moved


def write_meta(path: Path, meta: dict) -> None:
    path.with_name(f"{path.stem}.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    LAYERS.mkdir(parents=True, exist_ok=True)
    (SAMPLE / "alt_areas").mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------ zone d'étude
    # Rectangle 2000 m x 1500 m = 3 000 000 m² = 300 ha.
    area = gpd.GeoDataFrame(
        {"nom": ["Zone d'étude fictive de Valbrume"]},
        geometry=[place(box(-1000, -750, 1000, 750))],
        crs=LOCAL_CRS,
    ).to_crs("EPSG:4326")
    area_path = SAMPLE / "study_area.geojson"
    area.to_file(area_path, driver="GeoJSON")
    write_meta(
        area_path,
        {
            "name": "Zone d'étude fictive de Valbrume",
            "description": "Rectangle de 2000 m x 1500 m placé volontairement en mer.",
            "provenance": FICTIF,
            "date": "2026-11-09",
            "license": LICENCE,
            "is_fictitious": True,
            "known_limitations": ["Zone fictive : aucune réalité géographique."],
        },
    )

    # Zone alternative sans aucune donnée (à 10 km à l'est) : cas « aucune intersection ».
    alt = gpd.GeoDataFrame(
        {"nom": ["Zone fictive hors données"]},
        geometry=[place(box(9000, -500, 10000, 500))],
        crs=LOCAL_CRS,
    ).to_crs("EPSG:4326")
    alt_path = SAMPLE / "alt_areas" / "zone_hors_donnees.geojson"
    alt.to_file(alt_path, driver="GeoJSON")
    write_meta(
        alt_path,
        {
            "name": "Zone fictive hors données",
            "provenance": FICTIF,
            "date": "2026-11-09",
            "license": LICENCE,
            "is_fictitious": True,
        },
    )

    # ------------------------------------------------------------ cours d'eau (GeoJSON, EPSG:4326)
    rivers = gpd.GeoDataFrame(
        {
            "id": ["R1", "R2", "R3", "R4"],
            "nom": [
                "Ruisseau fictif de la Brume",
                "Canal fictif du Nord",
                None,
                "Ru fictif lointain",
            ],
            "regime": ["permanent", "intermittent", "intermittent", "permanent"],
        },
        geometry=[
            place(LineString([(-1500, 200), (1500, 200)])),  # traverse : 2000 m dans la zone
            place(LineString([(-800, 900), (800, 900)])),  # hors zone, à 150 m du bord nord
            place(
                LineString([(400, 200), (400, -1200)])
            ),  # affluent : 950 m dans la zone, nom absent
            place(
                LineString([(3000, 3000), (4000, 3500)])
            ),  # éloigné : ni intersection, ni proximité
        ],
        crs=LOCAL_CRS,
    ).to_crs("EPSG:4326")
    rivers_path = LAYERS / "cours_eau_fictifs.geojson"
    rivers.to_file(rivers_path, driver="GeoJSON")
    write_meta(
        rivers_path,
        {
            "name": "Cours d'eau (fictif)",
            "theme": "hydrography",
            "description": "Tracés linéaires fictifs de cours d'eau.",
            "provenance": FICTIF,
            "date": "2026-11-09",
            "license": LICENCE,
            "scale_denominator": 10000,
            "status": "fictif — démonstration",
            "id_attribute": "id",
            "label_attribute": "nom",
            "expected_attributes": ["nom", "regime"],
            "is_fictitious": True,
            "known_limitations": ["Tracés schématiques, sans statut réglementaire."],
        },
    )

    # ------------------------------------------------------------ zones de vigilance (GPKG, EPSG:2154)
    vig = gpd.GeoDataFrame(
        {
            "id": ["V1", "V2", "V3"],
            "alea": ["fort", "modéré", "faible"],
            "statut": ["provisoire", "provisoire", "provisoire"],
            "date_ref": ["2019-06", "2019-06", "2019-06"],
        },
        geometry=[
            place(box(-1500, -300, -500, 500)),  # partiel : 500 x 800 = 400 000 m² dans la zone
            place(box(-500, -300, 600, 500)),  # entièrement inclus : 1100 x 800 = 880 000 m²
            place(box(2000, 0, 3000, 500)),  # à 1000 m : hors tampon de 200 m
        ],
        crs=LOCAL_CRS,
    ).to_crs("EPSG:2154")
    vig_path = LAYERS / "zones_vigilance_fictives.gpkg"
    if vig_path.exists():
        vig_path.unlink()
    vig.to_file(vig_path, layer="zones_vigilance", driver="GPKG")
    write_meta(
        vig_path,
        {
            "name": "Zones de vigilance inondation (fictives)",
            "theme": "flood_hazard",
            "description": "Zones de vigilance fictives issues d'une « modélisation simplifiée » imaginaire.",
            "provenance": FICTIF,
            "date": "2019-06",
            "license": LICENCE,
            "scale_denominator": 25000,
            "status": "provisoire",
            "id_attribute": "id",
            "label_attribute": "alea",
            "expected_attributes": ["alea", "statut", "date_ref"],
            "gpkg_layer": "zones_vigilance",
            "is_fictitious": True,
            "known_limitations": [
                "Couche fictive au statut « provisoire » (choisi pour tester les avertissements).",
                "Échelle de saisie 1/25 000 : ne pas interpréter les limites à l'échelle parcellaire.",
            ],
        },
    )

    # ------------------------------------------------------------ occupation du sol (GeoJSON, EPSG:4326)
    bowtie = Polygon([(1500, -200), (2500, 200), (2500, -200), (1500, 200), (1500, -200)])
    land = gpd.GeoDataFrame(
        {
            "id": ["L1", "L2", "L3", "L4", "L5", "L6"],
            "classe": [
                "Terres agricoles",
                "Zone humide (fictive)",
                "Boisement",
                "Zone urbanisée",
                "Prairie",
                "Inconnue",
            ],
        },
        geometry=[
            place(box(-1000, -750, 0, 0)),  # 750 000 m² (25 %)
            place(box(-1000, 0, 0, 750)),  # 750 000 m² (25 %)
            place(box(0, 0, 1000, 750)),  # 750 000 m² (25 %)
            place(box(0, -1000, 1600, 0)),  # dépasse : 750 000 m² dans la zone (25 %)
            place(bowtie, densify=False),  # géométrie INVALIDE (auto-intersection), hors zone
            None,  # géométrie VIDE
        ],
        crs=LOCAL_CRS,
    ).to_crs("EPSG:4326")
    land_path = LAYERS / "occupation_sol_fictive.geojson"
    land.to_file(land_path, driver="GeoJSON")
    # Licence volontairement absente : démontre l'avertissement « non renseignée ».
    write_meta(
        land_path,
        {
            "name": "Occupation du sol (fictive)",
            "theme": "land_use",
            "description": "Classes d'occupation du sol fictives.",
            "provenance": FICTIF,
            "date": "2026-11-09",
            "scale_denominator": 10000,
            "status": "fictif — démonstration",
            "id_attribute": "id",
            "label_attribute": "classe",
            "expected_attributes": ["classe"],
            "is_fictitious": True,
            "known_limitations": [
                "Contient volontairement une géométrie invalide (L5) et une géométrie vide (L6).",
            ],
        },
    )

    print(f"Centre du repère (UTM 30N) : E={E0:.1f} N={N0:.1f}")
    for p in sorted(SAMPLE.rglob("*")):
        if p.is_file() and p.suffix in {".geojson", ".gpkg", ".json"}:
            print(" -", p.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    main()
