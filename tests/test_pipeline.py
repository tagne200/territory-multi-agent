"""Tests de bout en bout : scénario complet, erreurs d'entrée, conformité et traçabilité."""

from __future__ import annotations

import json

import pytest

from territory_assistant import DISCLAIMER
from territory_assistant.cli import main as cli_main
from territory_assistant.evaluation import run_evaluation, traceability
from territory_assistant.models import AnalysisReport, AnalysisRequest
from territory_assistant.pipeline import run_analysis
from territory_assistant.reporting import write_outputs
from territory_assistant.reporting.json_report import load_report

from .conftest import QUESTION, ROOT, SAMPLE


def test_full_valid_scenario(sample_request, settings, tmp_path):
    out = run_analysis(sample_request, settings)
    r = out.report
    assert r.status == "à vérifier"
    assert {(f.feature_id, f.relation) for f in r.spatial_findings} == {
        ("R1", "intersects"),
        ("R2", "within_buffer"),
        ("R3", "intersects"),
        ("L1", "intersects"),
        ("L2", "intersects"),
        ("L3", "intersects"),
        ("L4", "intersects"),
        ("V1", "intersects"),
        ("V2", "intersects"),
    }
    assert all(c.passed for c in r.verification.checks)
    assert r.disclaimer == DISCLAIMER
    paths = write_outputs(out, tmp_path)
    assert set(paths) == {"map", "findings", "json", "markdown"}
    assert all(p.exists() and p.stat().st_size > 0 for p in paths.values())
    md = paths["markdown"].read_text(encoding="utf-8")
    assert "Prototype d'aide à l'analyse — résultats à vérifier par un spécialiste." in md
    # données manquantes et incertitudes AVANT les points à vérifier
    assert (
        md.index("## 6. Données manquantes")
        < md.index("## 7. Limites")
        < md.index("**Points à vérifier**")
    )
    gj = json.loads(paths["findings"].read_text(encoding="utf-8"))
    assert {f["properties"]["finding_id"] for f in gj["features"]} == {
        f.finding_id for f in r.spatial_findings
    }


def test_report_conforms_to_schema(sample_request, settings, tmp_path):
    out = run_analysis(sample_request, settings)
    paths = write_outputs(out, tmp_path)
    reloaded = load_report(paths["json"])
    assert isinstance(reloaded, AnalysisReport)
    assert (
        reloaded.model_dump() == AnalysisReport.model_validate(out.report.model_dump()).model_dump()
    )


def test_report_references_exist_in_registry(sample_request, settings):
    r = run_analysis(sample_request, settings).report
    registry = {s.source_id for s in r.sources}
    refs = {sid for s in r.statements + r.missing_information for sid in s.source_ids}
    refs |= {f.source_id for f in r.spatial_findings} | {e.source_id for e in r.document_evidence}
    refs |= {sid for rec in r.points_to_verify + r.human_verifications for sid in rec.source_ids}
    refs |= {sid for u in r.uncertainties for sid in u.related_source_ids}
    assert refs <= registry
    rate, ok, total = traceability(r)
    assert rate == 1.0 and total > 20
    for (
        s
    ) in r.sources:  # provenance et licence toujours présentes (éventuellement « non renseignée »)
        assert s.provenance and s.license and s.loaded_at


def test_unknown_zone_blocks_cleanly(settings, tmp_path):
    req = AnalysisRequest(
        question=QUESTION,
        study_area_path=SAMPLE / "inconnue.geojson",
        layer_paths=[SAMPLE / "layers" / "cours_eau_fictifs.geojson"],
        allowed_roots=[ROOT],
    )
    out = run_analysis(req, settings)
    assert out.report.status == "bloqué" and out.report.study_area is None
    assert any("introuvable" in m.text for m in out.report.missing_information)
    paths = write_outputs(out, tmp_path)
    assert "map" not in paths and paths["json"].exists()


def test_missing_layer_is_reported_not_fatal(settings):
    req = AnalysisRequest(
        question=QUESTION,
        study_area_path=SAMPLE / "study_area.geojson",
        layer_paths=[
            SAMPLE / "layers" / "cours_eau_fictifs.geojson",
            SAMPLE / "layers" / "absente.geojson",
        ],
        allowed_roots=[ROOT],
    )
    r = run_analysis(req, settings).report
    assert r.status == "à vérifier" and r.spatial_findings
    assert any("absente.geojson" in m.text for m in r.missing_information)


def test_read_error_layer_is_isolated(settings, tmp_path):
    bad = tmp_path / "corrompue.geojson"
    bad.write_text('{"type":"FeatureCollection","features":[{"type":"Feature"', encoding="utf-8")
    req = AnalysisRequest(
        question=QUESTION,
        study_area_path=SAMPLE / "study_area.geojson",
        layer_paths=[SAMPLE / "layers" / "cours_eau_fictifs.geojson", bad],
        allowed_roots=[ROOT, tmp_path],
    )
    r = run_analysis(req, settings).report
    err = [lm for lm in r.layers if lm.load_status == "error"]
    assert len(err) == 1 and "malformé" in err[0].error
    assert any(u.severity == "critical" and u.category == "coverage" for u in r.uncertainties)
    assert any(f.feature_id == "R1" for f in r.spatial_findings)


def test_path_outside_roots_is_refused_in_pipeline(settings, tmp_path):
    outside = tmp_path / "zone.geojson"
    outside.write_text(
        (SAMPLE / "study_area.geojson").read_text(encoding="utf-8"), encoding="utf-8"
    )
    req = AnalysisRequest(question=QUESTION, study_area_path=outside, allowed_roots=[ROOT])
    r = run_analysis(req, settings).report
    assert r.status == "bloqué"
    assert any("hors des répertoires autorisés" in m.text for m in r.missing_information)


def test_cli_demo_without_api_key(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(ROOT)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    code = cli_main(["demo", "--no-llm", "--quiet", "--out", str(tmp_path)])
    assert code == 0
    out = capsys.readouterr().out
    assert "statut : à vérifier" in out
    assert len(list(tmp_path.glob("TA-*/report.json"))) == 1


@pytest.mark.slow
def test_evaluation_cases_all_pass(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    summary = run_evaluation(ROOT / "evaluation" / "cases", tmp_path / "eval.json", root=ROOT)
    assert summary["nombre_de_cas"] >= 6 and summary["all_passed"], [
        (r["case_id"], r["controles"]) for r in summary["resultats"] if not r["reussi"]
    ]
