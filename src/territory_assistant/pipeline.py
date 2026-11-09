"""Orchestration explicite et observable des cinq agents.

Ordre fixe : cadrage -> SIG -> documents -> synthèse -> vérification.
Boucle bornée : si la vérification rejette une synthèse contenant du texte LLM, une
seule régénération est tentée avec le retour de l'agent de vérification ; en cas de
nouvel échec, la synthèse déterministe est utilisée et le rapport l'indique.
"""

from __future__ import annotations

import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

from territory_assistant import DISCLAIMER, __version__
from territory_assistant.agents.base import InputInventory, InputItem, RunContext
from territory_assistant.agents.document_agent import DocumentAgent
from territory_assistant.agents.scoping_agent import ScopingAgent
from territory_assistant.agents.spatial_agent import SpatialAgent
from territory_assistant.agents.synthesis_agent import SynthesisAgent
from territory_assistant.agents.verification_agent import VerificationAgent
from territory_assistant.config import (
    DOCUMENT_EXTENSIONS,
    LAYER_EXTENSIONS,
    STUDY_AREA_EXTENSIONS,
    Settings,
)
from territory_assistant.errors import InputFileError
from territory_assistant.llm import LLMClient, LLMError, build_llm_client
from territory_assistant.models import (
    AgentTrace,
    AnalysisReport,
    AnalysisRequest,
    DocumentSearchResult,
    SpatialAnalysisResult,
    Uncertainty,
)
from territory_assistant.safety import resolve_safe_path
from territory_assistant.source_registry import SourceRegistry, load_sidecar

T = TypeVar("T")
MAX_REGENERATIONS = 1


@dataclass
class PipelineOutput:
    report: AnalysisReport
    ctx: RunContext


def _item(
    raw: Path,
    kind: str,
    *,
    exts: set[str],
    max_mb: float,
    roots: list[Path],
    registry: SourceRegistry,
) -> InputItem:
    label = {"study_area": "zone d'étude", "gis_layer": "couche", "document": "document"}[kind]
    try:
        path = resolve_safe_path(
            raw, allowed_roots=roots, allowed_extensions=exts, max_mb=max_mb, label=label
        )
    except InputFileError as exc:
        return InputItem(requested=str(raw), display=Path(raw).name, error=str(exc))
    meta, meta_warnings = load_sidecar(path)
    ref = registry.register_file(kind=kind, path=path, meta=meta, meta_warnings=meta_warnings)
    return InputItem(
        requested=str(raw),
        display=ref.filename,
        path=path,
        meta=meta,
        meta_warnings=meta_warnings,
        source_id=ref.source_id,
    )


def build_inventory(
    request: AnalysisRequest, settings: Settings, roots: list[Path], registry: SourceRegistry
) -> InputInventory:
    """Contrôle chaque chemin et enregistre les fichiers valides dans le registre des sources."""
    registry.register_user_input("question", f"Question : {request.question.strip()[:150]}")
    if request.project_type:
        registry.register_user_input(
            "type_de_projet", f"Type de projet : {request.project_type.strip()[:150]}"
        )
    area = (
        _item(
            request.study_area_path,
            "study_area",
            exts=STUDY_AREA_EXTENSIONS,
            max_mb=settings.max_file_mb,
            roots=roots,
            registry=registry,
        )
        if request.study_area_path
        else None
    )
    layers = [
        _item(
            p,
            "gis_layer",
            exts=LAYER_EXTENSIONS,
            max_mb=settings.max_file_mb,
            roots=roots,
            registry=registry,
        )
        for p in request.layer_paths
    ]
    docs = [
        _item(
            p,
            "document",
            exts=DOCUMENT_EXTENSIONS,
            max_mb=settings.max_doc_mb,
            roots=roots,
            registry=registry,
        )
        for p in request.document_paths
    ]
    return InputInventory(
        question=request.question,
        project_type=request.project_type,
        area=area,
        layers=layers,
        documents=docs,
    )


def run_analysis(
    request: AnalysisRequest,
    settings: Settings | None = None,
    llm: LLMClient | None = None,
    log: Callable[[str], None] | None = None,
) -> PipelineOutput:
    """Exécute l'analyse complète et retourne le rapport validé (jamais d'exception pour
    une donnée manquante ou illisible : ces cas sont décrits dans le rapport)."""
    settings = settings or Settings.from_env()
    log = log or (lambda _msg: None)
    trace: list[AgentTrace] = []
    pipeline_warnings: list[str] = []

    if llm is None and settings.llm_provider != "none":
        try:
            llm = build_llm_client(settings)
        except LLMError as exc:
            pipeline_warnings.append(f"Mode LLM demandé mais indisponible ({exc.kind}) : {exc}")
            log(f"! LLM indisponible ({exc.kind}) : analyse en mode déterministe.")

    roots = [Path(r) for r in request.allowed_roots] or [Path.cwd()]
    registry = SourceRegistry(display_roots=roots)
    inventory = build_inventory(request, settings, roots, registry)
    ctx = RunContext(settings=settings, registry=registry, inventory=inventory)

    def timed(
        agent_name: str, fn: Callable[[], T], summarize: Callable[[T], tuple[str, list[str]]]
    ) -> T:
        started = datetime.now(UTC)
        t0 = time.perf_counter()
        result = fn()
        summary, warns = summarize(result)
        status = "warning" if warns else "ok"
        trace.append(
            AgentTrace(
                agent=agent_name,
                status=status,
                started_at=started,
                duration_ms=round((time.perf_counter() - t0) * 1000, 1),
                summary=summary,
                warnings=warns,
            )
        )
        log(f"[{len(trace)}] {agent_name} : {status} — {summary}")
        return result

    def skipped(agent_name: str, reason: str) -> None:
        trace.append(
            AgentTrace(
                agent=agent_name,
                status="skipped",
                started_at=datetime.now(UTC),
                duration_ms=0.0,
                summary=reason,
            )
        )
        log(f"[-] {agent_name} : ignoré — {reason}")

    # 1. Cadrage
    scoping = timed(
        ScopingAgent.name,
        lambda: ScopingAgent(llm).run(ctx),
        lambda r: (
            f"{len(r.missing_information)} information(s) manquante(s), "
            f"{len(r.blocking_issues)} blocage(s)",
            r.warnings + r.blocking_issues,
        ),
    )

    # 2. SIG
    if scoping.blocking_issues:
        spatial = SpatialAnalysisResult(
            study_area=None, blocking_error="; ".join(scoping.blocking_issues)
        )
        skipped(SpatialAgent.name, "zone d'étude indisponible")
    else:
        spatial = timed(
            SpatialAgent.name,
            lambda: SpatialAgent().run(ctx),
            lambda r: (
                f"{len(r.layers)} couche(s), {len(r.findings)} constat(s)"
                if not r.blocking_error
                else f"bloqué : {r.blocking_error}",
                r.warnings + ([r.blocking_error] if r.blocking_error else []),
            ),
        )
    blocked = spatial.study_area is None

    # 3. Documents
    if blocked:
        docs = DocumentSearchResult(no_result_message="Recherche non effectuée : analyse bloquée.")
        skipped(DocumentAgent.name, "analyse bloquée")
    else:
        docs = timed(
            DocumentAgent.name,
            lambda: DocumentAgent().run(ctx, scoping, spatial),
            lambda r: (
                f"{r.documents_loaded} document(s), {len(r.evidence)} extrait(s)",
                r.warnings,
            ),
        )

    # 4 + 5. Synthèse et vérification (boucle bornée)
    synth_agent, verif_agent = SynthesisAgent(llm), VerificationAgent()
    synth = timed(
        SynthesisAgent.name,
        lambda: synth_agent.run(ctx, scoping, spatial, docs),
        lambda r: (
            f"{len(r.statements)} affirmation(s), résumé par {r.summary_generated_by}",
            r.warnings,
        ),
    )
    verif = timed(
        VerificationAgent.name,
        lambda: verif_agent.run(ctx, spatial, docs, synth),
        lambda r: (f"statut : {r.status}", r.feedback),
    )
    extra_uncertainties: list[Uncertainty] = []
    attempts = 0
    while verif.regeneration_requested and attempts < MAX_REGENERATIONS:
        attempts += 1
        fb = verif.feedback
        synth = timed(
            f"{SynthesisAgent.name} (régénération {attempts})",
            lambda fb=fb: synth_agent.run(ctx, scoping, spatial, docs, feedback=fb),
            lambda r: (f"{len(r.statements)} affirmation(s)", r.warnings),
        )
        verif = timed(
            f"{VerificationAgent.name} (contrôle {attempts + 1})",
            lambda s=synth: verif_agent.run(ctx, spatial, docs, s),
            lambda r: (f"statut : {r.status}", r.feedback),
        )
    if verif.regeneration_requested:
        rejected = "; ".join(verif.feedback)
        synth = timed(
            f"{SynthesisAgent.name} (repli déterministe)",
            lambda: SynthesisAgent(None).run(ctx, scoping, spatial, docs),
            lambda r: ("synthèse par règles", r.warnings),
        )
        verif = timed(
            f"{VerificationAgent.name} (contrôle final)",
            lambda: verif_agent.run(ctx, spatial, docs, synth),
            lambda r: (f"statut : {r.status}", r.feedback),
        )
        extra_uncertainties.append(
            Uncertainty(
                uncertainty_id="UL-001",
                category="llm",
                severity="warning",
                description=f"Synthèse LLM rejetée par la vérification puis remplacée par la synthèse déterministe : {rejected}",
            )
        )

    if blocked:
        status = "bloqué"
    elif verif.status == "conforme":
        status = "contrôles automatiques passés"
    else:
        status = "à vérifier"

    for w in pipeline_warnings:
        extra_uncertainties.append(
            Uncertainty(
                uncertainty_id=f"UP-{len(extra_uncertainties) + 1:03d}",
                category="llm",
                severity="info",
                description=w,
            )
        )
    sa = spatial.study_area
    report = AnalysisReport(
        analysis_id=f"TA-{datetime.now(UTC):%Y%m%d-%H%M%S}-{secrets.token_hex(3)}",
        created_at=datetime.now(UTC),
        tool_version=__version__,
        mode=(f"LLM ({llm.provider} / {llm.model}) + règles" if llm else "sans LLM (déterministe)"),
        llm_model=llm.model if llm else None,
        status=status,  # type: ignore[arg-type]
        question=request.question,
        project_type=scoping.project_type,
        parameters={
            "buffer_m": settings.buffer_m,
            "crs_calcul": sa.crs_metric if sa else None,
            "crs_calcul_impose": settings.metric_crs,
            "max_area_km2": settings.max_area_km2,
            "doc_top_k": settings.doc_top_k,
            "stale_data_years": settings.stale_data_years,
            "regenerations_llm": attempts,
        },
        scoping=scoping,
        study_area=sa,
        sources=registry.all(),
        layers=spatial.layers,
        spatial_findings=spatial.findings,
        document_evidence=docs.evidence,
        document_search_note=docs.no_result_message,
        summary=synth.summary,
        summary_generated_by=synth.summary_generated_by,
        statements=synth.statements,
        missing_information=synth.missing_information,
        uncertainties=synth.uncertainties + verif.added_uncertainties + extra_uncertainties,
        points_to_verify=synth.points_to_verify,
        human_verifications=synth.human_verifications,
        verification=verif,
        agent_trace=trace,
        disclaimer=DISCLAIMER,
    )
    return PipelineOutput(report=report, ctx=ctx)
