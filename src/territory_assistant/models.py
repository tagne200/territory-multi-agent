"""Modèles Pydantic : entrées, sorties des agents et rapport final.

Tous les modèles interdisent les champs inattendus (extra="forbid") afin qu'une
sortie hors schéma — notamment celle d'un LLM — soit rejetée explicitement.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

NOT_PROVIDED = "non renseignée"

JsonScalar = str | int | float | bool | None


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- entrées


class AnalysisRequest(StrictModel):
    """Demande utilisateur, avant toute validation métier."""

    question: str = Field(min_length=1, max_length=2000)
    project_type: str | None = Field(default=None, max_length=200)
    study_area_path: Path | None = None
    layer_paths: list[Path] = Field(default_factory=list)
    document_paths: list[Path] = Field(default_factory=list)
    # Répertoires autorisés : tout fichier en dehors est refusé.
    allowed_roots: list[Path] = Field(default_factory=list)


class SidecarMetadata(StrictModel):
    """Métadonnées fournies à côté d'un fichier (<fichier>.meta.json)."""

    name: str | None = None
    theme: Literal["hydrography", "flood_hazard", "land_use", "other"] | None = None
    description: str | None = None
    provenance: str | None = None
    date: str | None = None
    license: str | None = None
    scale_denominator: int | None = Field(default=None, gt=0)
    status: str | None = None
    id_attribute: str | None = None
    label_attribute: str | None = None
    expected_attributes: list[str] = Field(default_factory=list)
    gpkg_layer: str | None = None
    known_limitations: list[str] = Field(default_factory=list)
    is_fictitious: bool | None = None


# --------------------------------------------------------------------------- provenance


class SourceReference(StrictModel):
    """Entrée du registre des sources."""

    source_id: str
    kind: Literal["gis_layer", "study_area", "document", "user_input"]
    filename: str
    title: str
    provenance: str = NOT_PROVIDED
    date_or_version: str = NOT_PROVIDED
    license: str = NOT_PROVIDED
    crs: str | None = None
    loaded_at: datetime
    sha256: str | None = None
    processing: list[str] = Field(default_factory=list)
    known_limitations: list[str] = Field(default_factory=list)
    is_fictitious: bool | None = None
    warnings: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- SIG


class Metric(StrictModel):
    name: str
    value: float
    unit: str
    crs: str | None = Field(default=None, description="CRS dans lequel la mesure a été calculée")


class StudyArea(StrictModel):
    source_id: str
    name: str
    crs_original: str
    crs_metric: str
    area_m2: float
    area_ha: float
    bbox_wgs84: tuple[float, float, float, float]
    centroid_wgs84: tuple[float, float]
    n_input_features: int
    geometry_wgs84: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)


class LayerMetadata(StrictModel):
    layer_id: str
    source_id: str
    name: str
    theme: str
    filename: str
    description: str = NOT_PROVIDED
    load_status: Literal["ok", "error"]
    error: str | None = None
    geometry_types: list[str] = Field(default_factory=list)
    feature_count_total: int = 0
    feature_count_used: int = 0
    crs_original: str | None = None
    crs_metric: str | None = None
    reprojected: bool = False
    invalid_geometries_fixed: int = 0
    empty_geometries_removed: int = 0
    attributes: list[str] = Field(default_factory=list)
    missing_attributes: dict[str, int] = Field(default_factory=dict)
    id_attribute: str | None = None
    label_attribute: str | None = None
    scale_denominator: int | None = None
    date: str = NOT_PROVIDED
    status: str = NOT_PROVIDED
    warnings: list[str] = Field(default_factory=list)


class SpatialFinding(StrictModel):
    """Constat calculé : relation entre une entité d'une couche et la zone d'étude."""

    finding_id: str
    layer_id: str
    source_id: str
    layer_name: str
    theme: str
    feature_id: str
    feature_label: str | None = None
    attributes: dict[str, JsonScalar] = Field(default_factory=dict)
    relation: Literal["intersects", "touches_boundary", "within_buffer"]
    geometry_type: str
    metrics: list[Metric] = Field(default_factory=list)
    distance_m: float | None = None
    operation: str
    parameters: dict[str, JsonScalar] = Field(default_factory=dict)
    crs_transformation: str
    warnings: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- documents


class DocumentEvidence(StrictModel):
    evidence_id: str
    source_id: str
    filename: str
    title: str
    section: str | None = None
    page: int | None = None
    chunk_id: str
    excerpt: str
    excerpt_truncated: bool = False
    score: float
    matched_terms: list[str] = Field(default_factory=list)
    related_themes: list[str] = Field(default_factory=list)
    suspicious_instructions: bool = False
    sent_to_llm: bool = False


# --------------------------------------------------------------------------- synthèse


StatementCategory = Literal[
    "computed_fact", "document_content", "interpretation", "missing_information"
]


class Statement(StrictModel):
    """Affirmation de la synthèse, rattachée à ses sources."""

    statement_id: str
    category: StatementCategory
    text: str
    source_ids: list[str] = Field(default_factory=list)
    based_on: list[str] = Field(
        default_factory=list, description="Identifiants de constats SIG / extraits / affirmations"
    )
    generated_by: Literal["rules", "llm"] = "rules"


class Uncertainty(StrictModel):
    uncertainty_id: str
    category: Literal[
        "data_quality",
        "crs",
        "scale",
        "date",
        "status",
        "provenance",
        "license",
        "coverage",
        "method",
        "document",
        "llm",
        "security",
    ]
    severity: Literal["info", "warning", "critical"]
    description: str
    related_source_ids: list[str] = Field(default_factory=list)


class Recommendation(StrictModel):
    recommendation_id: str
    kind: Literal["point_to_verify", "human_verification", "data_request"]
    text: str
    rationale: str
    based_on: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    generated_by: Literal["rules", "llm"] = "rules"
    validation_status: Literal["à valider par un spécialiste"] = "à valider par un spécialiste"


# --------------------------------------------------------------------------- agents


class ScopingResult(StrictModel):
    original_question: str
    reformulated_question: str
    project_type: str
    study_area_provided: bool
    layers_requested: int
    layer_themes: dict[str, str] = Field(default_factory=dict)
    documents_requested: int
    missing_information: list[str] = Field(default_factory=list)
    blocking_issues: list[str] = Field(default_factory=list)
    is_valid: bool
    generated_by: Literal["rules", "llm"] = "rules"
    warnings: list[str] = Field(default_factory=list)


class SpatialAnalysisResult(StrictModel):
    study_area: StudyArea | None
    layers: list[LayerMetadata] = Field(default_factory=list)
    findings: list[SpatialFinding] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    blocking_error: str | None = None


class DocumentSearchResult(StrictModel):
    query_terms: list[str] = Field(default_factory=list)
    documents_loaded: int = 0
    chunks_indexed: int = 0
    evidence: list[DocumentEvidence] = Field(default_factory=list)
    no_result_message: str | None = None
    warnings: list[str] = Field(default_factory=list)


class SynthesisResult(StrictModel):
    summary: str
    summary_generated_by: Literal["rules", "llm"] = "rules"
    statements: list[Statement] = Field(default_factory=list)
    missing_information: list[Statement] = Field(default_factory=list)
    points_to_verify: list[Recommendation] = Field(default_factory=list)
    human_verifications: list[Recommendation] = Field(default_factory=list)
    uncertainties: list[Uncertainty] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class Check(StrictModel):
    name: str
    passed: bool
    details: str = ""


class VerificationResult(StrictModel):
    status: Literal["conforme", "à vérifier", "non conforme"]
    checks: list[Check] = Field(default_factory=list)
    unsupported_statement_ids: list[str] = Field(default_factory=list)
    unknown_reference_ids: list[str] = Field(default_factory=list)
    metric_mismatches: list[str] = Field(default_factory=list)
    excerpt_mismatches: list[str] = Field(default_factory=list)
    forbidden_language: list[str] = Field(default_factory=list)
    added_uncertainties: list[Uncertainty] = Field(default_factory=list)
    regeneration_requested: bool = False
    feedback: list[str] = Field(default_factory=list)


class AgentTrace(StrictModel):
    agent: str
    status: Literal["ok", "warning", "error", "skipped"]
    started_at: datetime
    duration_ms: float
    summary: str
    warnings: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- rapport


ReportStatus = Literal["contrôles automatiques passés", "à vérifier", "bloqué"]


class AnalysisReport(StrictModel):
    """Rapport final. Les sections suivent l'ordre de lecture recommandé."""

    analysis_id: str
    created_at: datetime
    tool_version: str
    mode: str
    llm_model: str | None = None
    status: ReportStatus
    question: str
    project_type: str
    parameters: dict[str, JsonScalar] = Field(default_factory=dict)
    scoping: ScopingResult
    study_area: StudyArea | None = None
    sources: list[SourceReference] = Field(default_factory=list)
    layers: list[LayerMetadata] = Field(default_factory=list)
    spatial_findings: list[SpatialFinding] = Field(default_factory=list)
    document_evidence: list[DocumentEvidence] = Field(default_factory=list)
    document_search_note: str | None = None
    summary: str = ""
    summary_generated_by: Literal["rules", "llm"] = "rules"
    statements: list[Statement] = Field(default_factory=list)
    missing_information: list[Statement] = Field(default_factory=list)
    uncertainties: list[Uncertainty] = Field(default_factory=list)
    points_to_verify: list[Recommendation] = Field(default_factory=list)
    human_verifications: list[Recommendation] = Field(default_factory=list)
    verification: VerificationResult | None = None
    agent_trace: list[AgentTrace] = Field(default_factory=list)
    disclaimer: str = Field(min_length=20)
