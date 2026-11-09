"""Interface en ligne de commande.

Exemples :
    territory-assistant demo
    territory-assistant analyze --area data/sample/study_area.geojson \\
        --layers data/sample/layers --docs data/sample/documents \\
        --question "Quels éléments territoriaux doivent être examinés ?" --project-type "aménagement"
    territory-assistant evaluate
    territory-assistant schema docs/report_schema.json

Codes de sortie : 0 = rapport produit ; 2 = analyse bloquée ; 1 = erreur inattendue.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from territory_assistant import DISCLAIMER
from territory_assistant.config import DOCUMENT_EXTENSIONS, LAYER_EXTENSIONS, Settings
from territory_assistant.models import AnalysisRequest

DEMO_QUESTION = "Quels éléments territoriaux doivent être examinés avant une étude d'aménagement dans cette zone ?"
SAMPLE = Path("data/sample")


def _expand(paths: list[str], exts: set[str]) -> list[Path]:
    """Accepte des fichiers ou des répertoires (non récursif, ordre alphabétique, *.meta.json exclus)."""
    out: list[Path] = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            out += sorted(
                f
                for f in path.iterdir()
                if f.is_file() and f.suffix.lower() in exts and not f.name.endswith(".meta.json")
            )
        else:
            out.append(path)
    return out


def _settings(args: argparse.Namespace) -> Settings:
    s = Settings.from_env()
    updates = {}
    if getattr(args, "no_llm", False):
        updates["llm_provider"] = "none"
    if getattr(args, "llm", None):
        updates["llm_provider"] = args.llm
    if getattr(args, "buffer", None) is not None:
        updates["buffer_m"] = args.buffer
    if getattr(args, "metric_crs", None):
        updates["metric_crs"] = args.metric_crs
    return s.model_copy(update=updates) if updates else s


def _run(request: AnalysisRequest, settings: Settings, out_dir: Path, quiet: bool) -> int:
    from territory_assistant.pipeline import run_analysis
    from territory_assistant.reporting import write_outputs

    def log(msg: str) -> None:
        if not quiet:
            print(msg)

    print("Prototype d'aide à l'analyse — résultats à vérifier par un spécialiste.\n")
    output = run_analysis(request, settings, log=log)
    paths = write_outputs(output, out_dir)
    r = output.report
    print(f"\nAnalyse {r.analysis_id} — statut : {r.status} — mode : {r.mode}")
    print(
        f"Constats SIG : {len(r.spatial_findings)} | extraits documentaires : {len(r.document_evidence)} | "
        f"données manquantes : {len(r.missing_information)} | incertitudes : {len(r.uncertainties)}"
    )
    for name, p in paths.items():
        print(f"  {name:9s} -> {p.as_posix()}")
    print(f"\n{DISCLAIMER}")
    return 2 if r.status == "bloqué" else 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # accents sous Windows
    parser = argparse.ArgumentParser(
        prog="territory-assistant",
        description=(
            "Assistant multi-agents d'analyse préliminaire des contraintes territoriales. "
            "Prototype : résultats à vérifier par un spécialiste."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--out", default="reports", help="Répertoire de sortie (défaut : reports)")
    common.add_argument("--no-llm", action="store_true", help="Force le mode déterministe")
    common.add_argument(
        "--llm", choices=["none", "anthropic"], help="Fournisseur LLM (prioritaire sur .env)"
    )
    common.add_argument("--buffer", type=float, help="Tampon de proximité en mètres (défaut 200)")
    common.add_argument(
        "--metric-crs", help="CRS métrique imposé, ex. EPSG:2154 (défaut : UTM auto)"
    )
    common.add_argument("--quiet", action="store_true", help="N'affiche pas la trace des agents")

    sub.add_parser("demo", parents=[common], help="Scénario fictif de démonstration")

    an = sub.add_parser("analyze", parents=[common], help="Analyse d'une zone")
    an.add_argument("--area", required=True, help="Zone d'étude (GeoJSON ou GeoPackage)")
    an.add_argument("--layers", nargs="*", default=[], help="Fichiers ou répertoires de couches")
    an.add_argument("--docs", nargs="*", default=[], help="Fichiers ou répertoires de documents")
    an.add_argument("--question", required=True, help="Question posée (1 à 2000 caractères)")
    an.add_argument("--project-type", help="Type de projet (facultatif, signalé s'il manque)")
    an.add_argument(
        "--root",
        action="append",
        default=[],
        help="Répertoire autorisé (répétable). Défaut : répertoire courant.",
    )

    ev = sub.add_parser("evaluate", help="Exécute le jeu d'évaluation (mode sans LLM)")
    ev.add_argument("--cases", default="evaluation/cases", help="Répertoire des cas (*.json)")
    ev.add_argument(
        "--out", default="reports/evaluation_results.json", help="Fichier de résultats JSON"
    )

    sc = sub.add_parser("schema", help="Écrit le JSON Schema du rapport")
    sc.add_argument(
        "path", nargs="?", default="docs/report_schema.json", help="Fichier de sortie du schéma"
    )

    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            req = AnalysisRequest(
                question=DEMO_QUESTION,
                project_type="aménagement (étude préliminaire)",
                study_area_path=SAMPLE / "study_area.geojson",
                layer_paths=_expand([str(SAMPLE / "layers")], LAYER_EXTENSIONS),
                document_paths=_expand([str(SAMPLE / "documents")], DOCUMENT_EXTENSIONS),
                allowed_roots=[Path.cwd()],
            )
            return _run(req, _settings(args), Path(args.out), args.quiet)
        if args.command == "analyze":
            req = AnalysisRequest(
                question=args.question,
                project_type=args.project_type,
                study_area_path=Path(args.area),
                layer_paths=_expand(args.layers, LAYER_EXTENSIONS),
                document_paths=_expand(args.docs, DOCUMENT_EXTENSIONS),
                allowed_roots=[Path(r) for r in args.root] or [Path.cwd()],
            )
            return _run(req, _settings(args), Path(args.out), args.quiet)
        if args.command == "evaluate":
            from territory_assistant.evaluation import run_evaluation

            summary = run_evaluation(Path(args.cases), Path(args.out))
            return 0 if summary["all_passed"] else 1
        if args.command == "schema":
            from territory_assistant.reporting.json_report import write_json_schema

            p = write_json_schema(Path(args.path))
            print(f"Schéma écrit : {p.as_posix()}")
            return 0
    except Exception as exc:  # dernier filet : message lisible, pas de trace brute
        print(f"Erreur : {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
