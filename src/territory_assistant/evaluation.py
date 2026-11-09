"""Évaluation reproductible sur un petit jeu de cas documentés (evaluation/cases/*.json).

Mesures (définies ici, calculées à chaque exécution — aucun chiffre n'est annoncé sans elles) :
- conformite_schema : le rapport JSON se relit et se revalide avec le modèle Pydantic ;
- tracabilite : part des affirmations/recommandations dont toutes les références existent
  et qui ont au moins une référence lorsqu'elles en exigent une ;
- precision_sig / rappel_sig : sur les couples (source, entité, relation) attendus ;
- faux_positifs : entités qui ne doivent PAS apparaître (ex. R4, V3) mais apparaissent ;
- exactitude_mesures : part des mesures attendues retrouvées à la tolérance près ;
- rappel_documentaire : part des sections attendues présentes dans les extraits non suspects ;
- garde-fous : passages suspects signalés, aucune affirmation LLM non vérifiée conservée.
Les valeurs attendues sont analytiques (géométries conçues en mètres), donc indépendantes du code.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from territory_assistant.config import Settings
from territory_assistant.llm import LLMOutputError, ScriptedLLMClient
from territory_assistant.models import AnalysisReport, AnalysisRequest
from territory_assistant.pipeline import run_analysis
from territory_assistant.reporting.json_report import load_report, write_json


def traceability(report: AnalysisReport) -> tuple[float, int, int]:
    """(taux, nb conformes, nb total) — références existantes et présentes quand requises."""
    sources = {s.source_id for s in report.sources}
    ids = (
        {f.finding_id for f in report.spatial_findings}
        | {e.evidence_id for e in report.document_evidence}
        | {s.statement_id for s in report.statements + report.missing_information}
        | {r.recommendation_id for r in report.points_to_verify + report.human_verifications}
    )
    ok = total = 0
    for s in report.statements:
        total += 1
        needs = s.category in ("computed_fact", "document_content")
        refs_ok = all(x in sources for x in s.source_ids) and all(b in ids for b in s.based_on)
        has = bool(s.source_ids) if needs else bool(s.based_on and s.source_ids)
        ok += int(refs_ok and has)
    for r in report.points_to_verify + report.human_verifications:
        total += 1
        ok += int(
            all(x in sources for x in r.source_ids)
            and all(b in ids for b in r.based_on)
            and bool(r.source_ids or r.based_on)
        )
    for f in report.spatial_findings:
        total += 1
        ok += int(f.source_id in sources)
    return (ok / total if total else 1.0), ok, total


def _pairs(report: AnalysisReport) -> set[tuple[str, str, str]]:
    return {(f.source_id, f.feature_id, f.relation) for f in report.spatial_findings}


def evaluate_case(case: dict[str, Any], root: Path) -> dict[str, Any]:
    req = case["request"]
    settings = Settings(**case.get("settings", {}))
    llm = None
    if "llm_script" in case:
        script = [
            LLMOutputError("sortie simulée hors schéma") if x == "INVALID" else x
            for x in case["llm_script"]
        ]
        llm = ScriptedLLMClient(script)
    request = AnalysisRequest(
        question=req["question"],
        project_type=req.get("project_type"),
        study_area_path=root / req["study_area"] if req.get("study_area") else None,
        layer_paths=[root / p for p in req.get("layers", [])],
        document_paths=[root / p for p in req.get("documents", [])],
        allowed_roots=[root],
    )
    report = run_analysis(request, settings, llm=llm).report
    exp = case["expected"]
    res: dict[str, Any] = {"case_id": case["case_id"], "status": report.status}
    checks: dict[str, bool] = {}

    # Conformité au schéma (aller-retour JSON)
    with tempfile.TemporaryDirectory() as tmp:
        p = write_json(report, Path(tmp) / "r.json")
        try:
            load_report(p)
            res["conformite_schema"] = 1.0
        except Exception:  # noqa: BLE001 - toute erreur = non conforme
            res["conformite_schema"] = 0.0
    checks["schema"] = res["conformite_schema"] == 1.0

    rate, ok, total = traceability(report)
    res["tracabilite"] = round(rate, 4)
    res["tracabilite_detail"] = f"{ok}/{total}"
    checks["tracabilite"] = rate == 1.0

    checks["statut"] = report.status in exp.get("status_in", [report.status])

    # SIG
    expected_pairs = set()
    for rel in ("intersects", "within_buffer"):
        for src, ids in exp.get(rel, {}).items():
            expected_pairs |= {(src, fid, rel) for fid in ids}
    found = _pairs(report)
    if expected_pairs or exp.get("no_findings"):
        tp = len(found & expected_pairs)
        res["precision_sig"] = (
            round(tp / len(found), 4) if found else (1.0 if not expected_pairs else 0.0)
        )
        res["rappel_sig"] = round(tp / len(expected_pairs), 4) if expected_pairs else 1.0
        checks["sig_exact"] = found == expected_pairs
    forbidden = {(src, fid) for src, ids in exp.get("must_not_appear", {}).items() for fid in ids}
    fp = sorted(f"{s}/{f}" for s, f, _ in found if (s, f) in forbidden)
    res["faux_positifs"] = fp
    checks["faux_positifs"] = not fp

    # Mesures
    m_ok, m_total, m_err = 0, 0, []
    for m in exp.get("metrics", []):
        m_total += 1
        f = next(
            (
                x
                for x in report.spatial_findings
                if x.source_id == m["source_id"] and x.feature_id == m["feature_id"]
            ),
            None,
        )
        val = next((mm.value for mm in f.metrics if mm.name == m["name"]), None) if f else None
        tol = abs(m["value"]) * m.get("tolerance_pct", 0.5) / 100
        if val is not None and abs(val - m["value"]) <= max(tol, 0.01):
            m_ok += 1
        else:
            m_err.append(f"{m['feature_id']}.{m['name']} attendu {m['value']} obtenu {val}")
    if m_total:
        res["exactitude_mesures"] = round(m_ok / m_total, 4)
        res["ecarts_mesures"] = m_err
        checks["mesures"] = m_ok == m_total

    # Documents
    clean = [e for e in report.document_evidence if not e.suspicious_instructions]
    if "expected_doc_sections" in exp:
        got = {e.section for e in clean}
        want = set(exp["expected_doc_sections"])
        res["rappel_documentaire"] = round(len(got & want) / len(want), 4) if want else 1.0
        res["extraits_hors_attendus"] = sorted(s or "(sans section)" for s in got - want)
        checks["documents"] = want <= got
    if "suspicious_sources" in exp:
        flagged = {e.source_id for e in report.document_evidence if e.suspicious_instructions}
        leaked = [
            s.statement_id
            for s in report.statements
            if any(
                b in {e.evidence_id for e in report.document_evidence if e.suspicious_instructions}
                for b in s.based_on
            )
        ]
        checks["injection_signalee"] = set(exp["suspicious_sources"]) <= flagged and not leaked
    if exp.get("missing_contains"):
        texts = " ".join(m.text for m in report.missing_information)
        checks["donnees_manquantes"] = all(t in texts for t in exp["missing_contains"])
    if exp.get("no_llm_content_kept"):
        kept = [s.statement_id for s in report.statements if s.generated_by == "llm"]
        kept += [p.recommendation_id for p in report.points_to_verify if p.generated_by == "llm"]
        checks["llm_rejete"] = not kept and report.summary_generated_by == "rules"
    if exp.get("llm_content_kept"):
        kept = [s for s in report.statements if s.generated_by == "llm"]
        checks["llm_conserve"] = bool(kept) and report.summary_generated_by == "llm"
    if report.verification and report.status != "bloqué":
        checks["verification_controles"] = all(c.passed for c in report.verification.checks)

    res["controles"] = checks
    res["reussi"] = all(checks.values())
    return res


def run_evaluation(cases_dir: Path, out_path: Path, root: Path | None = None) -> dict[str, Any]:
    root = (root or Path.cwd()).resolve()
    cases = [
        json.loads(p.read_text(encoding="utf-8")) for p in sorted(Path(cases_dir).glob("*.json"))
    ]
    results = [evaluate_case(c, root) for c in cases]
    n = len(results)
    summary = {
        "nombre_de_cas": n,
        "cas_reussis": sum(r["reussi"] for r in results),
        "conformite_schema_moyenne": round(sum(r["conformite_schema"] for r in results) / n, 4)
        if n
        else None,
        "tracabilite_moyenne": round(sum(r["tracabilite"] for r in results) / n, 4) if n else None,
        "all_passed": all(r["reussi"] for r in results),
        "resultats": results,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"{'cas':28s} {'statut':30s} {'schéma':>6s} {'traçab.':>8s} {'préc.':>6s} {'rappel':>6s} {'mesures':>7s} {'docs':>5s}  résultat"
    )

    def fmt(r: dict[str, Any], k: str) -> str:
        return f"{r[k]:.2f}" if isinstance(r.get(k), float) else "—"

    for r in results:

        def f(k: str, r: dict[str, Any] = r) -> str:
            return fmt(r, k)

        print(
            f"{r['case_id']:28s} {r['status']:30s} {f('conformite_schema'):>6s} {f('tracabilite'):>8s} "
            f"{f('precision_sig'):>6s} {f('rappel_sig'):>6s} {f('exactitude_mesures'):>7s} "
            f"{f('rappel_documentaire'):>5s}  {'OK' if r['reussi'] else 'ÉCHEC ' + str([k for k, v in r['controles'].items() if not v])}"
        )
    print(f"\n{summary['cas_reussis']}/{n} cas réussis — résultats : {out_path.as_posix()}")
    return summary
