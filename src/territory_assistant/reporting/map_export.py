"""Carte de synthèse (PNG, matplotlib) et export GeoJSON des constats.

La carte est tracée dans le CRS métrique de calcul : les distances affichées par la
barre d'échelle sont donc en mètres réels (à la déformation du CRS près).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # rendu sans écran
import geopandas as gpd  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

from territory_assistant.pipeline import PipelineOutput  # noqa: E402
from territory_assistant.spatial.analysis import findings_to_geodataframe  # noqa: E402

THEME_COLORS = {
    "hydrography": "#1f77b4",
    "flood_hazard": "#d62728",
    "land_use": "#2ca02c",
    "other": "#7f7f7f",
}


def export_findings_geojson(output: PipelineOutput, path: Path) -> Path:
    a = output.ctx.artifacts
    gdf = findings_to_geodataframe(
        a["layers_gdf"],
        output.report.spatial_findings,
        a["area_geom"],
        a["metric_crs"],
        a["id_columns"],
    )
    gdf.to_file(path, driver="GeoJSON")
    return path


def export_map(output: PipelineOutput, path: Path) -> Path:
    r, a = output.report, output.ctx.artifacts
    area_geom, crs = a["area_geom"], a["metric_crs"]
    buffer_m = output.ctx.settings.buffer_m
    hit_ids = {(f.layer_id, f.feature_id) for f in r.spatial_findings}

    fig, ax = plt.subplots(figsize=(11, 7.5), dpi=130)
    legend: list = []
    for lm in r.layers:
        layer = a["layers_gdf"].get(lm.layer_id)
        if layer is None or layer.empty:
            continue
        color = THEME_COLORS.get(lm.theme, THEME_COLORS["other"])
        col = lm.id_attribute
        ids = (
            layer[col].astype(str)
            if col
            else pd.Series([f"index {i}" for i in layer.index], index=layer.index)
        )
        is_hit = ids.map(lambda v, lid=lm.layer_id: (lid, v) in hit_ids).astype(bool)
        polys = layer[layer.geom_type.isin(["Polygon", "MultiPolygon"])]
        lines = layer[layer.geom_type.isin(["LineString", "MultiLineString"])]
        pts = layer[layer.geom_type.isin(["Point", "MultiPoint"])]
        if not polys.empty:
            polys.plot(ax=ax, facecolor=color, alpha=0.18, edgecolor=color, linewidth=0.6)
            polys[is_hit.loc[polys.index]].plot(
                ax=ax, facecolor="none", edgecolor=color, linewidth=1.8
            )
            legend.append(Patch(facecolor=color, alpha=0.4, edgecolor=color, label=lm.name))
        if not lines.empty:
            lines.plot(ax=ax, color=color, linewidth=1.0, alpha=0.6)
            lines[is_hit.loc[lines.index]].plot(ax=ax, color=color, linewidth=2.6)
            legend.append(Line2D([0], [0], color=color, linewidth=2.6, label=lm.name))
        if not pts.empty:
            pts.plot(ax=ax, color=color, markersize=25)
            legend.append(Line2D([0], [0], marker="o", color=color, linestyle="", label=lm.name))

    area = gpd.GeoSeries([area_geom], crs=crs)
    if buffer_m > 0:
        area.buffer(buffer_m).boundary.plot(ax=ax, color="#555555", linewidth=1, linestyle="--")
        legend.append(
            Line2D([0], [0], color="#555555", linestyle="--", label=f"Tampon {buffer_m:g} m")
        )
    area.boundary.plot(ax=ax, color="black", linewidth=2.2)
    legend.append(Line2D([0], [0], color="black", linewidth=2.2, label="Zone d'étude"))

    # étiquettes des constats
    fgdf = findings_to_geodataframe(
        a["layers_gdf"], r.spatial_findings, area_geom, crs, a["id_columns"]
    ).to_crs(crs)
    for _, row in fgdf.iterrows():
        if row.geometry is None or row.geometry.is_empty:
            continue
        p = row.geometry.representative_point()
        ax.annotate(
            row["feature_id"],
            (p.x, p.y),
            fontsize=7,
            ha="center",
            va="center",
            bbox={
                "boxstyle": "round,pad=0.15",
                "fc": "white",
                "ec": "#333333",
                "lw": 0.4,
                "alpha": 0.85,
            },
        )

    minx, miny, maxx, maxy = area_geom.buffer(max(buffer_m, 1) * 1.6).bounds
    ax.set_xlim(minx, maxx)
    ax.set_ylim(miny, maxy)
    ax.set_aspect("equal")
    ax.ticklabel_format(style="plain", useOffset=False)
    ax.tick_params(labelsize=6)

    # barre d'échelle simple (mètres, CRS projeté)
    span = maxx - minx
    bar = 10 ** int(len(str(int(span / 4))) - 1)
    bar = bar * 5 if bar * 5 < span / 3 else bar
    x0, y0 = minx + span * 0.05, miny + (maxy - miny) * 0.05
    ax.plot([x0, x0 + bar], [y0, y0], color="black", linewidth=3)
    ax.text(x0 + bar / 2, y0 + (maxy - miny) * 0.015, f"{bar:g} m", ha="center", fontsize=7)

    fictive = any(s.is_fictitious for s in r.sources)
    title = f"Carte de synthèse — {r.study_area.name if r.study_area else ''}"
    ax.set_title(title + ("\nDONNÉES FICTIVES — démonstration" if fictive else ""), fontsize=10)
    ax.legend(
        handles=legend, loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=7, framealpha=0.9
    )
    fig.text(
        0.01,
        0.01,
        f"CRS de calcul et d'affichage : {r.parameters.get('crs_calcul')} — "
        f"Analyse {r.analysis_id}\nPrototype d'aide à l'analyse — résultats à vérifier par un spécialiste.",
        fontsize=6.5,
        va="bottom",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(path)
    plt.close(fig)
    return path
