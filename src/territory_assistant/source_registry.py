"""Registre des sources : provenance, licence, CRS et traitements de chaque entrée.

Toute affirmation du rapport doit pointer vers un identifiant présent ici ; l'agent de
vérification contrôle cette règle.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from territory_assistant.models import NOT_PROVIDED, SidecarMetadata, SourceReference

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    import unicodedata

    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return _SLUG_RE.sub("_", t).strip("_") or "source"


def sidecar_path(path: Path) -> Path:
    """`couche.geojson` -> `couche.meta.json` (même répertoire)."""
    return path.with_name(f"{path.stem}.meta.json")


def load_sidecar(path: Path) -> tuple[SidecarMetadata | None, list[str]]:
    """Charge les métadonnées associées à un fichier, si elles existent.

    Retourne (métadonnées ou None, avertissements). Un fichier de métadonnées malformé
    n'interrompt pas l'analyse : il est signalé.
    """
    meta_file = sidecar_path(path)
    if not meta_file.is_file():
        return None, [
            f"Aucun fichier de métadonnées ({meta_file.name}) : provenance, date et licence non renseignées."
        ]
    if meta_file.stat().st_size > 1024 * 1024:
        return None, [f"Fichier de métadonnées ignoré (trop volumineux) : {meta_file.name}"]
    try:
        data = json.loads(meta_file.read_text(encoding="utf-8"))
        return SidecarMetadata.model_validate(data), []
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        return None, [
            f"Métadonnées illisibles ou hors schéma ({meta_file.name}) : {type(exc).__name__}"
        ]


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _display_path(path: Path, roots: list[Path]) -> str:
    """Chemin relatif à une racine autorisée (évite d'exposer des chemins absolus)."""
    for root in roots:
        try:
            return path.resolve().relative_to(Path(root).resolve()).as_posix()
        except ValueError:
            continue
    return path.name


class SourceRegistry:
    """Registre en mémoire des sources utilisées pendant une analyse."""

    def __init__(self, display_roots: list[Path] | None = None) -> None:
        self._sources: dict[str, SourceReference] = {}
        self._roots = display_roots or []

    # ------------------------------------------------------------------ enregistrement
    def _unique_id(self, prefix: str, stem: str) -> str:
        base = f"{prefix}:{slugify(stem)}"
        sid, n = base, 2
        while sid in self._sources:
            sid, n = f"{base}_{n}", n + 1
        return sid

    def register_file(
        self,
        *,
        kind: str,
        path: Path,
        meta: SidecarMetadata | None,
        meta_warnings: list[str] | None = None,
    ) -> SourceReference:
        prefix = {"gis_layer": "layer", "study_area": "area", "document": "doc"}[kind]
        sid = self._unique_id(prefix, path.stem)
        warnings = list(meta_warnings or [])
        m = meta or SidecarMetadata()

        def _val(value: str | None, label: str) -> str:
            if value and value.strip():
                return value.strip()
            warnings.append(f"{label} non renseignée pour « {path.name} ».")
            return NOT_PROVIDED

        ref = SourceReference(
            source_id=sid,
            kind=kind,  # type: ignore[arg-type]
            filename=_display_path(path, self._roots),
            title=(m.name or path.stem),
            provenance=_val(m.provenance, "Provenance"),
            date_or_version=_val(m.date, "Date ou version"),
            license=_val(m.license, "Licence"),
            loaded_at=datetime.now(UTC),
            sha256=file_sha256(path),
            known_limitations=list(m.known_limitations),
            is_fictitious=m.is_fictitious,
            warnings=warnings,
        )
        self._sources[sid] = ref
        return ref

    def register_user_input(self, name: str, description: str) -> SourceReference:
        sid = self._unique_id("input", name)
        ref = SourceReference(
            source_id=sid,
            kind="user_input",
            filename="(saisie utilisateur)",
            title=description,
            provenance="saisie utilisateur",
            date_or_version=datetime.now(UTC).date().isoformat(),
            license="sans objet",
            loaded_at=datetime.now(UTC),
        )
        self._sources[sid] = ref
        return ref

    # ------------------------------------------------------------------ mise à jour
    def add_processing(self, source_id: str, step: str) -> None:
        ref = self._sources[source_id]
        if step not in ref.processing:
            ref.processing.append(step)

    def add_warning(self, source_id: str, warning: str) -> None:
        ref = self._sources[source_id]
        if warning not in ref.warnings:
            ref.warnings.append(warning)

    def set_crs(self, source_id: str, crs: str | None) -> None:
        self._sources[source_id].crs = crs

    # ------------------------------------------------------------------ lecture
    def get(self, source_id: str) -> SourceReference:
        return self._sources[source_id]

    def __contains__(self, source_id: object) -> bool:
        return source_id in self._sources

    def ids(self) -> set[str]:
        return set(self._sources)

    def all(self) -> list[SourceReference]:
        return list(self._sources.values())
