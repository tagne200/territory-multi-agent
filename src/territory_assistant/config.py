"""Configuration du prototype, lue depuis les variables d'environnement.

Aucune clé secrète n'est stockée ici : la clé Anthropic est lue directement par le
SDK officiel depuis l'environnement (ANTHROPIC_API_KEY) lorsque le mode LLM est actif.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Extensions acceptées (liste blanche).
LAYER_EXTENSIONS = {".geojson", ".json", ".gpkg"}
DOCUMENT_EXTENSIONS = {".md", ".txt", ".pdf"}
STUDY_AREA_EXTENSIONS = {".geojson", ".json", ".gpkg"}

# Thèmes de couches reconnus et thèmes attendus pour une analyse préliminaire
# "aménagement / gestion de l'eau". Ce sont des règles de cadrage, pas des faits.
KNOWN_THEMES = ("hydrography", "flood_hazard", "land_use", "other")
EXPECTED_THEMES = ("hydrography", "flood_hazard", "land_use")
THEME_LABELS = {
    "hydrography": "réseau hydrographique",
    "flood_hazard": "zones inondables / de vigilance",
    "land_use": "occupation du sol",
    "other": "autre",
}

# Mots-clés documentaires associés aux thèmes (servent à construire les requêtes).
THEME_KEYWORDS: dict[str, list[str]] = {
    "hydrography": ["cours d'eau", "ruisseau", "rivière", "berge", "recul", "écoulement"],
    "flood_hazard": ["inondation", "inondable", "aléa", "vigilance", "crue", "zone de vigilance"],
    "land_use": ["occupation du sol", "zone humide", "agricole", "boisement", "urbanisée"],
    "other": [],
}


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    return default if value is None or value.strip() == "" else value.strip()


class Settings(BaseModel):
    """Paramètres du prototype (valeurs par défaut sûres, mode sans LLM)."""

    llm_provider: Literal["none", "anthropic"] = "none"
    llm_model: str = "claude-opus-5-5"
    llm_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    llm_timeout_s: float = Field(default=60.0, gt=0, le=600)
    llm_max_retries: int = Field(default=2, ge=0, le=5)
    llm_server_fallback: bool = True

    max_file_mb: float = Field(default=50.0, gt=0)
    max_features: int = Field(default=50_000, gt=0)
    max_area_km2: float = Field(default=100.0, gt=0)

    buffer_m: float = Field(default=200.0, ge=0, le=5000)
    metric_crs: str | None = None
    stale_data_years: int = Field(default=5, ge=1)

    max_doc_mb: float = Field(default=10.0, gt=0)
    doc_top_k: int = Field(default=8, ge=1, le=50)
    doc_min_score: float = Field(default=1.0, ge=0)

    @field_validator("metric_crs")
    @classmethod
    def _empty_to_none(cls, v: str | None) -> str | None:
        return v or None

    @classmethod
    def from_env(cls, env_file: str | Path | None = ".env") -> Settings:
        """Construit la configuration depuis l'environnement (et un .env local facultatif)."""
        if env_file and Path(env_file).is_file():
            from dotenv import load_dotenv

            load_dotenv(env_file, override=False)
        return cls(
            llm_provider=_env("TA_LLM_PROVIDER", "none").lower(),  # type: ignore[arg-type]
            llm_model=_env("TA_LLM_MODEL", "claude-opus-5-5"),
            llm_effort=_env("TA_LLM_EFFORT", "medium").lower(),  # type: ignore[arg-type]
            llm_timeout_s=float(_env("TA_LLM_TIMEOUT_S", "60")),
            llm_max_retries=int(_env("TA_LLM_MAX_RETRIES", "2")),
            llm_server_fallback=_env("TA_LLM_SERVER_FALLBACK", "true").lower()
            in {"1", "true", "yes"},
            max_file_mb=float(_env("TA_MAX_FILE_MB", "50")),
            max_features=int(_env("TA_MAX_FEATURES", "50000")),
            max_area_km2=float(_env("TA_MAX_AREA_KM2", "100")),
            buffer_m=float(_env("TA_BUFFER_M", "200")),
            metric_crs=_env("TA_METRIC_CRS", "") or None,
            stale_data_years=int(_env("TA_STALE_DATA_YEARS", "5")),
        )
