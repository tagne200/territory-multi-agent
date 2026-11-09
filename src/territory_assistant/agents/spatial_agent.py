"""Agent 2 — Analyse SIG (100 % déterministe, aucun LLM).

Contrat (en lieu et place d'un prompt système) :
- charge la zone et les couches avec GeoPandas ; refuse un CRS absent ;
- reprojette dans un CRS projeté métrique unique avant toute mesure ;
- détecte les entités qui intersectent la zone ou sont à moins de `buffer_m` ;
- retourne identifiants, attributs, métriques (avec unités et CRS), avertissements ;
- ne formule aucune conclusion réglementaire.
Une couche illisible n'interrompt pas l'analyse : elle est marquée `load_status="error"`.
"""

from __future__ import annotations

from territory_assistant.agents.base import RunContext
from territory_assistant.errors import TerritoryAssistantError
from territory_assistant.models import LayerMetadata, SpatialAnalysisResult
from territory_assistant.spatial.analysis import analyze_layer, prepare_layer, prepare_study_area
from territory_assistant.spatial.loader import read_vector


class SpatialAgent:
    name = "Agent 2 — Analyse SIG"

    def run(self, ctx: RunContext) -> SpatialAnalysisResult:
        s, reg, inv = ctx.settings, ctx.registry, ctx.inventory
        warnings: list[str] = []
        area_item = inv.area
        if area_item is None or area_item.error or area_item.path is None:
            return SpatialAnalysisResult(
                study_area=None, blocking_error="Zone d'étude indisponible."
            )

        # ------------------------------------------------------------ zone
        try:
            gdf, rw = read_vector(area_item.path, max_features=s.max_features)
            study, area_geom, metric_crs, aw = prepare_study_area(
                gdf,
                source_id=area_item.source_id or "",
                name=(
                    area_item.meta.name
                    if area_item.meta and area_item.meta.name
                    else area_item.display
                ),
                metric_crs_setting=s.metric_crs,
                max_area_km2=s.max_area_km2,
            )
        except TerritoryAssistantError as exc:
            if area_item.source_id:
                reg.add_warning(area_item.source_id, str(exc))
            return SpatialAnalysisResult(study_area=None, blocking_error=str(exc))
        study.warnings[:0] = rw
        sid = area_item.source_id or ""
        reg.set_crs(sid, study.crs_original)
        reg.add_processing(sid, f"lecture ({area_item.path.suffix})")
        reg.add_processing(sid, "contrôle CRS et validité des géométries")
        reg.add_processing(
            sid, f"reprojection {study.crs_original} → {study.crs_metric} pour les mesures"
        )
        for w in study.warnings:
            reg.add_warning(sid, w)

        ctx.artifacts.update(
            area_geom=area_geom, metric_crs=metric_crs, layers_gdf={}, id_columns={}
        )

        # ------------------------------------------------------------ couches
        layers: list[LayerMetadata] = []
        findings = []
        for n, item in enumerate(inv.layers, start=1):
            layer_id = f"L{n:02d}"
            if item.error or item.path is None:
                continue  # déjà signalé par le cadrage (fichier absent / refusé)
            meta = item.meta
            try:
                raw, rw = read_vector(
                    item.path,
                    max_features=s.max_features,
                    gpkg_layer=meta.gpkg_layer if meta else None,
                )
                metric_gdf, lm = prepare_layer(
                    raw,
                    layer_id=layer_id,
                    source_id=item.source_id or "",
                    filename=item.display,
                    meta=meta,
                    metric_crs=metric_crs,
                    read_warnings=rw,
                )
            except TerritoryAssistantError as exc:
                msg = str(exc)
                warnings.append(msg)
                if item.source_id:
                    reg.add_warning(item.source_id, msg)
                layers.append(
                    LayerMetadata(
                        layer_id=layer_id,
                        source_id=item.source_id or "",
                        name=(meta.name if meta and meta.name else item.display),
                        theme=(meta.theme if meta and meta.theme else "other"),
                        filename=item.display,
                        load_status="error",
                        error=msg,
                    )
                )
                continue

            src = item.source_id or ""
            reg.set_crs(src, lm.crs_original)
            reg.add_processing(src, "contrôle CRS et validité des géométries")
            if lm.invalid_geometries_fixed:
                reg.add_processing(
                    src, f"réparation make_valid de {lm.invalid_geometries_fixed} géométrie(s)"
                )
            if lm.reprojected:
                reg.add_processing(src, f"reprojection {lm.crs_original} → {lm.crs_metric}")
            layer_findings = analyze_layer(
                metric_gdf,
                lm,
                area_geom=area_geom,
                area_m2=study.area_m2,
                buffer_m=s.buffer_m,
                id_prefix=f"F-{layer_id}",
            )
            reg.add_processing(
                src,
                f"intersection avec la zone et recherche de proximité (tampon {s.buffer_m:g} m)",
            )
            for w in lm.warnings:
                reg.add_warning(src, w)
            layers.append(lm)
            findings.extend(layer_findings)
            ctx.artifacts["layers_gdf"][layer_id] = metric_gdf
            ctx.artifacts["id_columns"][layer_id] = lm.id_attribute

        return SpatialAnalysisResult(
            study_area=study, layers=layers, findings=findings, warnings=warnings
        )
