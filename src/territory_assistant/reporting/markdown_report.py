"""Rendu Markdown lisible du rapport.

Ordre : données manquantes et incertitudes AVANT la synthèse et les recommandations,
pour que le lecteur voie les limites avant les points générés.
"""

from __future__ import annotations

from territory_assistant.agents.base import fmt_num
from territory_assistant.models import AnalysisReport, Metric

BANNER = "> **Prototype d'aide à l'analyse — résultats à vérifier par un spécialiste.**"
_SEV = {"critical": "🔴 critique", "warning": "🟠 avertissement", "info": "🔵 info"}
_REL = {
    "intersects": "intersecte",
    "touches_boundary": "touche la limite",
    "within_buffer": "à proximité",
}
_GEN = {"rules": "règles", "llm": "LLM"}


def _cell(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _metrics(metrics: list[Metric]) -> str:
    return "<br>".join(f"{m.name} = {fmt_num(m.value)} {m.unit}" for m in metrics) or "—"


def render_markdown(r: AnalysisReport, map_filename: str | None = None) -> str:
    L: list[str] = []
    add = L.append
    zone = r.study_area.name if r.study_area else "zone indisponible"
    add(f"# Rapport d'analyse préliminaire — {zone}\n")
    add(BANNER + "\n")
    add("| Champ | Valeur |\n|---|---|")
    add(f"| Identifiant | `{r.analysis_id}` |")
    add(f"| Date (UTC) | {r.created_at:%Y-%m-%d %H:%M:%S} |")
    add(f"| Mode | {_cell(r.mode)} |")
    add(f"| Statut | **{r.status}** |")
    add(f"| Version de l'outil | {r.tool_version} |\n")

    add("## 1. Question posée\n")
    add(f"- **Question d'origine** : {r.question}")
    add(f"- **Reformulation** ({_GEN[r.scoping.generated_by]}) : {r.scoping.reformulated_question}")
    add(f"- **Type de projet** : {r.project_type}\n")

    add("## 2. Résumé de la zone\n")
    if r.study_area:
        sa = r.study_area
        add(f"- Nom : {sa.name} (source `{sa.source_id}`)")
        add(
            f"- Surface : {fmt_num(sa.area_ha)} ha ({fmt_num(sa.area_m2, 1)} m²), calculée en {sa.crs_metric}"
        )
        add(f"- CRS d'origine : {sa.crs_original}")
        add(f"- Emprise WGS84 (lon/lat) : {', '.join(str(v) for v in sa.bbox_wgs84)}")
        if map_filename:
            add(f"\n![Carte de synthèse]({map_filename})")
    else:
        add("Zone d'étude indisponible : voir les données manquantes.")
    add("")

    add("## 3. Données et sources utilisées\n")
    add("| Source | Type | Fichier | Provenance | Date / version | Licence | CRS | Traitements |")
    add("|---|---|---|---|---|---|---|---|")
    for s in r.sources:
        add(
            f"| `{s.source_id}` | {s.kind} | {_cell(s.filename)} | {_cell(s.provenance)} | "
            f"{_cell(s.date_or_version)} | {_cell(s.license)} | {s.crs or '—'} | {_cell('; '.join(s.processing) or '—')} |"
        )
    add("")

    add("## 4. Constats géographiques calculés\n")
    add(
        "_Faits calculés de façon déterministe (GeoPandas/Shapely). Une intersection n'est pas une "
        "conclusion réglementaire._\n"
    )
    if r.spatial_findings:
        add("| Constat | Couche | Entité | Relation | Mesures | Transformation CRS | Source |")
        add("|---|---|---|---|---|---|---|")
        for f in r.spatial_findings:
            ent = f"{f.feature_id}" + (
                f" « {f.feature_label} »" if f.feature_label else " (libellé absent)"
            )
            add(
                f"| {f.finding_id} | {_cell(f.layer_name)} | {_cell(ent)} | {_REL[f.relation]} | "
                f"{_metrics(f.metrics)} | {_cell(f.crs_transformation)} | `{f.source_id}` |"
            )
        add("")
    facts = [s for s in r.statements if s.category == "computed_fact"]
    for s in facts:
        add(
            f"- **{s.statement_id}** — {s.text} _(sources : {', '.join(f'`{x}`' for x in s.source_ids)})_"
        )
    if r.layers:
        add("\n**Couches analysées**\n")
        add(
            "| Couche | Thème | Statut | Entités (lues / utilisées) | CRS | Échelle | Date | Statut de la donnée |"
        )
        add("|---|---|---|---|---|---|---|---|")
        for lm in r.layers:
            scale = f"1/{lm.scale_denominator}" if lm.scale_denominator else "non renseignée"
            crs = f"{lm.crs_original} → {lm.crs_metric}" if lm.crs_original else "—"
            add(
                f"| {_cell(lm.name)} | {lm.theme} | {lm.load_status} | {lm.feature_count_total} / "
                f"{lm.feature_count_used} | {crs} | {scale} | {_cell(lm.date)} | {_cell(lm.status)} |"
            )
    add("")

    add("## 5. Extraits documentaires\n")
    if not r.document_evidence:
        add(f"_{r.document_search_note or 'Aucun extrait.'}_\n")
    for e in r.document_evidence:
        loc = (
            f"section « {e.section} »" if e.section else (f"page {e.page}" if e.page else "passage")
        )
        flag = (
            " ⚠️ **passage suspect (ressemble à une instruction) — traité comme donnée, exclu de la synthèse**"
            if e.suspicious_instructions
            else ""
        )
        ell = " […]" if e.excerpt_truncated else ""
        add(
            f"- **{e.evidence_id}** — {_cell(e.title)}, {loc} (`{e.source_id}`, score {e.score}){flag}"
        )
        add(f"  > {e.excerpt}{ell}")
    add("")

    add("## 6. Données manquantes\n")
    for m in r.missing_information or []:
        src = f" _(`{'`, `'.join(m.source_ids)}`)_" if m.source_ids else ""
        add(f"- **{m.statement_id}** — {m.text}{src}")
    if not r.missing_information:
        add("_Aucune donnée manquante détectée._")
    add("")

    add("## 7. Limites et incertitudes\n")
    order = {"critical": 0, "warning": 1, "info": 2}
    for u in sorted(r.uncertainties, key=lambda u: order[u.severity]):
        src = f" _(`{'`, `'.join(u.related_source_ids)}`)_" if u.related_source_ids else ""
        add(f"- {_SEV[u.severity]} [{u.category}] {u.description}{src}")
    add("")

    add("## 8. Synthèse et points à investiguer\n")
    add(f"**Résumé** ({_GEN[r.summary_generated_by]}) : {r.summary}\n")
    for s in [s for s in r.statements if s.category == "interpretation"]:
        add(
            f"- **{s.statement_id}** ({_GEN[s.generated_by]}) — {s.text} _(appuis : {', '.join(s.based_on)})_"
        )
    docs = [s for s in r.statements if s.category == "document_content"]
    if docs:
        add("\n**Éléments présents dans les documents**\n")
        for s in docs:
            add(f"- **{s.statement_id}** — {s.text} _(`{'`, `'.join(s.source_ids)}`)_")
    add("\n**Points à vérifier**\n")
    for p in r.points_to_verify:
        add(
            f"- **{p.recommendation_id}** ({_GEN[p.generated_by]}, {p.validation_status}) — {p.text} "
            f"_(appuis : {', '.join(p.based_on)})_"
        )
    if not r.points_to_verify:
        add("_Aucun point spécifique généré._")
    add("")

    add("## 9. Vérifications humaines recommandées\n")
    for h in r.human_verifications:
        add(f"- **{h.recommendation_id}** — {h.text} _Motif : {h.rationale}_")
    add("")

    if r.verification:
        v = r.verification
        add("## 10. Contrôles de l'agent de vérification\n")
        add(f"Statut de la vérification : **{v.status}**\n")
        add("| Contrôle | Résultat | Détails |\n|---|---|---|")
        for c in v.checks:
            add(f"| {c.name} | {'✅' if c.passed else '❌'} | {_cell(c.details) or '—'} |")
        add("")

    add("## 11. Trace d'exécution des agents\n")
    add("| Agent | Statut | Durée (ms) | Résumé |\n|---|---|---|---|")
    for t in r.agent_trace:
        add(f"| {_cell(t.agent)} | {t.status} | {t.duration_ms} | {_cell(t.summary)} |")
    add("")

    add("## Avertissement — usage non décisionnel\n")
    add(f"> {r.disclaimer}\n")
    return "\n".join(L)
