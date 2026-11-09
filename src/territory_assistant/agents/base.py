"""Contexte d'exécution partagé et utilitaires communs aux agents."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from territory_assistant.config import Settings
from territory_assistant.models import SidecarMetadata
from territory_assistant.source_registry import SourceRegistry


@dataclass
class InputItem:
    """Fichier demandé par l'utilisateur, après contrôle du chemin."""

    requested: str
    display: str
    path: Path | None = None
    meta: SidecarMetadata | None = None
    meta_warnings: list[str] = field(default_factory=list)
    error: str | None = None
    source_id: str | None = None


@dataclass
class InputInventory:
    question: str
    project_type: str | None
    area: InputItem | None
    layers: list[InputItem]
    documents: list[InputItem]


@dataclass
class RunContext:
    settings: Settings
    registry: SourceRegistry
    inventory: InputInventory
    # Artefacts non sérialisés (géométries, passages complets) utiles à la carte et à la vérification.
    artifacts: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- nombres

NNBSP = "\u202f"  # espace fine insécable (séparateur de milliers français)


def fmt_num(value: float, decimals: int = 2) -> str:
    """Format français : 3 000 000 ; 13,33. Les zéros décimaux inutiles sont retirés."""
    if abs(value - round(value)) < 10 ** (-decimals) / 2:
        s = f"{round(value):,d}"
    else:
        s = f"{value:,.{decimals}f}".rstrip("0").rstrip(".")
    return s.replace(",", " ").replace(".", ",").replace(" ", NNBSP)


# Nombres « autonomes » : on ignore ceux collés à une lettre, « : », « - », « / », « _ »
# (identifiants R1, F-001, EPSG:32630, échelle 1/25 000…).
_NUM_RE = re.compile(
    r"(?<![\w:/\-.,\u202f\u00a0])(?<!\d[\u202f\u00a0 ])"
    r"(\d{1,3}(?:[\u202f\u00a0 ]\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)"
    r"(?![\w:/\-]|[.,]\d)"
)


def extract_numbers(text: str) -> list[float]:
    """Extrait les nombres d'un texte en français (séparateurs fins ou espaces, virgule décimale)."""
    out: list[float] = []
    for m in _NUM_RE.finditer(text):
        raw = re.sub(r"[\u202f\u00a0 ]", "", m.group(1)).replace(",", ".")
        try:
            out.append(float(raw))
        except ValueError:
            continue
    return out


def number_supported(value: float, allowed: set[float], rel_tol: float = 0.005) -> bool:
    """Vrai si `value` correspond (à l'arrondi près) à une valeur calculée autorisée."""
    return any(abs(value - a) <= max(0.011, rel_tol * abs(a)) for a in allowed)
