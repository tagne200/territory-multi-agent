"""Agent 5 — Vérification critique (déterministe).

Contrat (en lieu et place d'un prompt système) :
1. champs obligatoires présents ;
2. toute affirmation factuelle a une source, toute interprétation s'appuie sur un identifiant ;
3. toutes les références existent (registre des sources, constats, extraits, affirmations) ;
4. chaque extrait documentaire existe mot pour mot dans le document chargé ;
5. chaque nombre annoncé correspond à une valeur calculée par le moteur SIG
   (ou figurant dans un extrait / fait cité) ;
6. aucun langage décisionnel (« autorisé », « sans risque », « conforme »…) ;
7. ajout d'avertissements sur la qualité des données (date, échelle, statut, CRS, licence…).
Résultat : « conforme », « à vérifier » (avertissements) ou « non conforme » (contrôles
1–6 en échec) ; dans ce dernier cas, régénération demandée si du contenu LLM est en cause.
"""

from __future__ import annotations

import re
from datetime import date

from territory_assistant.agents.base import RunContext, extract_numbers, number_supported
from territory_assistant.models import (
    NOT_PROVIDED,
    Check,
    DocumentSearchResult,
    Recommendation,
    SpatialAnalysisResult,
    SpatialFinding,
    Statement,
    SynthesisResult,
    Uncertainty,
    VerificationResult,
)

FORBIDDEN_PATTERNS = [
    r"\bprojet\s+(est\s+|serait\s+)?(autoris|accept|valid[ée])",
    r"\b(est|sont|serait|seraient)\s+(autoris[ée]e?s?|interdite?s?|conformes?)\b",
    r"\bsans\s+(aucun\s+)?risques?\b",
    r"\baucun\s+risque\b",
    r"\bgaranti(t|e|r|s)?\b",
    r"\bcertifi(e|é|ée|er)\b",
    r"\b(in)?constructibles?\b",
]
_FORBIDDEN_RE = [re.compile(p, re.IGNORECASE) for p in FORBIDDEN_PATTERNS]
_QUOTED_RE = re.compile(r"«[^»]*»")
COARSE_SCALE = 25_000


def _strip_quotes(text: str) -> str:
    """Retire les segments entre guillemets (noms de couches, libellés, titres)."""
    return _QUOTED_RE.sub(" ", text)


def find_forbidden(text: str) -> list[str]:
    return [m.group(0) for rx in _FORBIDDEN_RE for m in rx.finditer(_strip_quotes(text))]


class VerificationAgent:
    name = "Agent 5 — Vérification critique"

    # ------------------------------------------------------------------ nombres autorisés
    @staticmethod
    def _finding_values(findings: list[SpatialFinding]) -> set[float]:
        vals: set[float] = set()
        sums: dict[str, float] = {}
        for f in findings:
            for m in f.metrics:
                vals.add(m.value)
                sums[m.name] = sums.get(m.name, 0.0) + m.value
            if f.distance_m is not None:
                vals.add(f.distance_m)
        vals.update(round(v, 2) for v in sums.values())
        vals.add(float(len(findings)))
        return vals

    def _base_allowed(self, ctx: RunContext, spatial: SpatialAnalysisResult) -> set[float]:
        allowed = {float(i) for i in range(11)}  # petits dénombrements (limite documentée)
        allowed.add(float(ctx.settings.buffer_m))
        if spatial.study_area:
            allowed.update({spatial.study_area.area_m2, spatial.study_area.area_ha})
        return allowed

    # ------------------------------------------------------------------ données
    def _data_uncertainties(
        self, ctx: RunContext, spatial: SpatialAnalysisResult, docs: DocumentSearchResult
    ) -> list[Uncertainty]:
        out: list[Uncertainty] = []
        year_now = date.today().year

        def add(cat: str, sev: str, text: str, sources: list[str]) -> None:
            out.append(
                Uncertainty(
                    uncertainty_id=f"UV-{len(out) + 1:03d}",
                    category=cat,  # type: ignore[arg-type]
                    severity=sev,
                    description=text,
                    related_source_ids=sources,
                )
            )  # type: ignore[arg-type]

        sa = spatial.study_area
        if sa:
            for w in sa.warnings:
                if "automatiquement" in w or "domaine de validité" in w:
                    add("crs", "info" if "automatiquement" in w else "warning", w, [sa.source_id])
        for lm in spatial.layers:
            src = [lm.source_id]
            if lm.load_status == "error":
                add("coverage", "critical", f"Couche « {lm.name} » non analysée : {lm.error}", src)
                continue
            m = re.search(r"(19|20)\d{2}", lm.date or "")
            if lm.date == NOT_PROVIDED or not m:
                add(
                    "date",
                    "warning",
                    f"Couche « {lm.name} » : date non renseignée, actualité inconnue.",
                    src,
                )
            elif int(m.group(0)) < year_now - ctx.settings.stale_data_years:
                add(
                    "date",
                    "warning",
                    f"Couche « {lm.name} » datée de {lm.date} (plus de "
                    f"{ctx.settings.stale_data_years} ans) : vérifier l'existence d'une version plus récente.",
                    src,
                )
            if "provisoire" in (lm.status or "").lower():
                add(
                    "status",
                    "warning",
                    f"Couche « {lm.name} » au statut « {lm.status} » : ne pas la traiter "
                    "comme une référence approuvée.",
                    src,
                )
            if lm.scale_denominator is None:
                add(
                    "scale",
                    "info",
                    f"Couche « {lm.name} » : échelle de saisie non renseignée.",
                    src,
                )
            elif lm.scale_denominator >= COARSE_SCALE:
                add(
                    "scale",
                    "warning",
                    f"Couche « {lm.name} » saisie au 1/{lm.scale_denominator} : limites "
                    "indicatives, insuffisantes pour une lecture à l'échelle de la parcelle.",
                    src,
                )
            if lm.invalid_geometries_fixed:
                add(
                    "data_quality",
                    "warning",
                    f"Couche « {lm.name} » : {lm.invalid_geometries_fixed} géométrie(s) "
                    "invalide(s) réparée(s) automatiquement ; forme à contrôler.",
                    src,
                )
            if lm.empty_geometries_removed:
                add(
                    "data_quality",
                    "info",
                    f"Couche « {lm.name} » : {lm.empty_geometries_removed} géométrie(s) "
                    "vide(s) ignorée(s).",
                    src,
                )
            if lm.missing_attributes:
                add(
                    "data_quality",
                    "warning",
                    f"Couche « {lm.name} » : attributs incomplets "
                    f"({', '.join(lm.missing_attributes)}).",
                    src,
                )
            if lm.reprojected:
                add(
                    "crs",
                    "info",
                    f"Couche « {lm.name} » reprojetée de {lm.crs_original} vers {lm.crs_metric} "
                    "avant calcul.",
                    src,
                )
        fict, lic, prov = [], [], []
        for s in ctx.registry.all():
            if s.kind == "user_input":
                continue
            if s.is_fictitious:
                fict.append(s.source_id)
            if s.license == NOT_PROVIDED:
                lic.append(s.source_id)
            if s.provenance == NOT_PROVIDED:
                prov.append(s.source_id)
        if fict:
            add(
                "provenance",
                "info",
                "Sources déclarées FICTIVES : résultats de démonstration sans valeur réelle.",
                fict,
            )
        if lic:
            add(
                "license",
                "warning",
                "Licence non renseignée : conditions de réutilisation inconnues.",
                lic,
            )
        if prov:
            add(
                "provenance",
                "warning",
                "Provenance non renseignée : origine des données à établir.",
                prov,
            )
        if not [e for e in docs.evidence if not e.suspicious_instructions]:
            add(
                "document",
                "warning",
                "Aucun extrait documentaire exploitable : synthèse fondée sur les seules couches.",
                [],
            )
        return out

    # ------------------------------------------------------------------ run
    def run(
        self,
        ctx: RunContext,
        spatial: SpatialAnalysisResult,
        docs: DocumentSearchResult,
        synth: SynthesisResult,
    ) -> VerificationResult:
        checks: list[Check] = []
        feedback: list[str] = []
        recs: list[Recommendation] = synth.points_to_verify + synth.human_verifications
        all_statements: list[Statement] = synth.statements + synth.missing_information

        # 1. champs obligatoires
        problems = []
        if not synth.summary.strip():
            problems.append("résumé vide")
        if spatial.study_area and not any(s.category == "computed_fact" for s in synth.statements):
            problems.append("aucun fait calculé")
        if spatial.study_area and not synth.human_verifications:
            problems.append("aucune vérification humaine recommandée")
        problems += [
            f"{r.recommendation_id} sans justification" for r in recs if not r.rationale.strip()
        ]
        checks.append(
            Check(name="champs_obligatoires", passed=not problems, details="; ".join(problems))
        )
        feedback += problems

        # 2. affirmations sans source
        suspicious_ev = {e.evidence_id for e in docs.evidence if e.suspicious_instructions}
        unsupported = []
        for s in synth.statements:
            factual_without_source = (
                s.category in ("computed_fact", "document_content") and not s.source_ids
            )
            interp_unsupported = s.category == "interpretation" and (
                not s.based_on or not s.source_ids or bool(set(s.based_on) & suspicious_ev)
            )
            if factual_without_source or interp_unsupported:
                unsupported.append(s.statement_id)
        unsupported += [r.recommendation_id for r in synth.points_to_verify if not r.based_on]
        checks.append(
            Check(
                name="affirmations_sourcees", passed=not unsupported, details=", ".join(unsupported)
            )
        )
        if unsupported:
            feedback.append(
                f"Affirmations sans source ou appuyées sur un passage suspect : {', '.join(unsupported)}"
            )

        # 3. références existantes
        known = (
            {f.finding_id for f in spatial.findings}
            | {e.evidence_id for e in docs.evidence}
            | {s.statement_id for s in all_statements}
            | {r.recommendation_id for r in recs}
        )
        reg = ctx.registry
        unknown: list[str] = []
        for item in [*all_statements, *recs]:
            unknown += [sid for sid in item.source_ids if sid not in reg]
            unknown += [b for b in item.based_on if b not in known]
        unknown += [f.source_id for f in spatial.findings if f.source_id not in reg]
        unknown += [e.source_id for e in docs.evidence if e.source_id not in reg]
        unknown += [
            sid for u in synth.uncertainties for sid in u.related_source_ids if sid not in reg
        ]
        unknown = sorted(set(unknown))
        checks.append(
            Check(name="references_existantes", passed=not unknown, details=", ".join(unknown))
        )
        if unknown:
            feedback.append(f"Identifiants inexistants cités : {', '.join(unknown)}")

        # 4. extraits verbatim
        store = ctx.artifacts.get("documents", {})
        excerpt_bad: list[str] = []
        ev_by_id = {e.evidence_id: e for e in docs.evidence}
        for e in docs.evidence:
            doc = store.get(e.source_id)
            chunk = next((c for c in doc.chunks if c.chunk_id == e.chunk_id), None) if doc else None
            if chunk is None or e.excerpt not in chunk.text:
                excerpt_bad.append(e.evidence_id)
        for s in synth.statements:
            if s.category == "document_content":
                for b in s.based_on:
                    ev = ev_by_id.get(b)
                    if ev is None or ev.excerpt not in s.text:
                        excerpt_bad.append(s.statement_id)
        checks.append(
            Check(name="extraits_verbatim", passed=not excerpt_bad, details=", ".join(excerpt_bad))
        )
        if excerpt_bad:
            feedback.append(f"Extraits non retrouvés mot pour mot : {', '.join(excerpt_bad)}")

        # 5. cohérence des chiffres
        f_by_id = {f.finding_id: f for f in spatial.findings}
        # Seules les affirmations produites par RÈGLES peuvent justifier un chiffre : un texte LLM
        # ne doit jamais servir de justification à un autre texte LLM (justification circulaire).
        st_by_id = {s.statement_id: s for s in synth.statements if s.generated_by == "rules"}
        base = self._base_allowed(ctx, spatial)
        mismatches: list[str] = []

        def allowed_for(based_on: list[str]) -> set[float]:
            allowed = set(base)
            refs = [f_by_id[b] for b in based_on if b in f_by_id]
            allowed |= self._finding_values(refs)
            for b in based_on:
                if b in st_by_id:
                    st = st_by_id[b]
                    allowed.update(extract_numbers(_strip_quotes(st.text)))
                    allowed |= self._finding_values(
                        [f_by_id[x] for x in st.based_on if x in f_by_id]
                    )
                if b in ev_by_id:
                    allowed.update(extract_numbers(ev_by_id[b].excerpt))
            return allowed

        to_check: list[tuple[str, str, list[str]]] = [
            (s.statement_id, s.text, s.based_on)
            for s in synth.statements
            if s.category == "computed_fact" or s.generated_by == "llm"
        ]
        to_check += [
            (r.recommendation_id, r.text, r.based_on) for r in recs if r.generated_by == "llm"
        ]
        if synth.summary_generated_by == "llm":
            all_ids = [f.finding_id for f in spatial.findings] + list(st_by_id) + list(ev_by_id)
            global_allowed = allowed_for(all_ids) | {
                float(len(spatial.findings)),
                float(len(docs.evidence)),
                float(len(spatial.layers)),
                float(sum(1 for f in spatial.findings if f.relation == "intersects")),
                float(sum(1 for f in spatial.findings if f.relation == "within_buffer")),
            }
            for n in extract_numbers(_strip_quotes(synth.summary)):
                if not number_supported(n, global_allowed):
                    mismatches.append(f"résumé : valeur {n:g} absente des calculs")
        for ident, text, based_on in to_check:
            allowed = allowed_for(based_on)
            for n in extract_numbers(_strip_quotes(text)):
                if not number_supported(n, allowed):
                    mismatches.append(f"{ident} : valeur {n:g} absente des calculs cités")
        checks.append(
            Check(
                name="coherence_des_chiffres", passed=not mismatches, details="; ".join(mismatches)
            )
        )
        if mismatches:
            feedback.append("Chiffres non justifiés par les calculs : " + "; ".join(mismatches))

        # 6. langage décisionnel
        forbidden: list[str] = []
        texts = [
            (s.statement_id, s.text) for s in synth.statements if s.category != "document_content"
        ]
        texts += [(r.recommendation_id, r.text) for r in recs] + [("résumé", synth.summary)]
        for ident, text in texts:
            forbidden += [f"{ident} : « {hit} »" for hit in find_forbidden(text)]
        checks.append(
            Check(
                name="langage_non_decisionnel", passed=not forbidden, details="; ".join(forbidden)
            )
        )
        if forbidden:
            feedback.append("Formulations décisionnelles interdites : " + "; ".join(forbidden))

        # 7. qualité des données
        added = self._data_uncertainties(ctx, spatial, docs)
        checks.append(
            Check(
                name="avertissements_donnees",
                passed=True,
                details=f"{len(added)} avertissement(s) ajouté(s)",
            )
        )

        failed = [c for c in checks if not c.passed]
        uses_llm = synth.summary_generated_by == "llm" or any(
            x.generated_by == "llm" for x in [*synth.statements, *synth.points_to_verify]
        )
        severe = [
            u for u in [*synth.uncertainties, *added] if u.severity in ("warning", "critical")
        ]
        status = "non conforme" if failed else ("à vérifier" if severe else "conforme")
        return VerificationResult(
            status=status,  # type: ignore[arg-type]
            checks=checks,
            unsupported_statement_ids=unsupported,
            unknown_reference_ids=unknown,
            metric_mismatches=mismatches,
            excerpt_mismatches=excerpt_bad,
            forbidden_language=forbidden,
            added_uncertainties=added,
            regeneration_requested=bool(failed) and uses_llm,
            feedback=feedback,
        )
