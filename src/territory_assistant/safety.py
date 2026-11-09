"""Garde-fous d'entrée : chemins, tailles, formats et texte ressemblant à des instructions.

Principe : le contenu des fichiers est traité comme des DONNÉES. Rien de ce qui est lu
dans un document ne peut modifier les règles du prototype ; on se contente ici de
détecter et signaler les passages suspects.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from territory_assistant.errors import InputFileError


def resolve_safe_path(
    path: str | Path,
    *,
    allowed_roots: list[Path],
    allowed_extensions: set[str],
    max_mb: float,
    label: str = "fichier",
) -> Path:
    """Valide un chemin d'entrée et retourne sa forme absolue résolue.

    Refuse : fichier absent, répertoire, extension hors liste blanche, fichier trop
    volumineux, chemin situé hors des répertoires autorisés (y compris via « .. » ou
    lien symbolique, puisque le chemin est résolu avant la comparaison).
    """
    raw = Path(path)
    try:
        resolved = raw.expanduser().resolve(strict=False)
    except (OSError, RuntimeError) as exc:  # boucle de liens, chemin invalide
        raise InputFileError(f"Chemin de {label} invalide : {raw}") from exc

    if allowed_roots:
        roots = [Path(r).expanduser().resolve() for r in allowed_roots]
        if not any(resolved == r or r in resolved.parents for r in roots):
            raise InputFileError(
                f"Chemin de {label} refusé (hors des répertoires autorisés) : {raw}"
            )
    if not resolved.exists():
        raise InputFileError(f"{label.capitalize()} introuvable : {raw}")
    if not resolved.is_file():
        raise InputFileError(f"{label.capitalize()} attendu, mais ce n'est pas un fichier : {raw}")
    ext = resolved.suffix.lower()
    if ext not in allowed_extensions:
        raise InputFileError(
            f"Format de {label} non accepté ({ext or 'sans extension'}) : {raw.name}. "
            f"Formats acceptés : {', '.join(sorted(allowed_extensions))}"
        )
    size_mb = resolved.stat().st_size / (1024 * 1024)
    if size_mb > max_mb:
        raise InputFileError(
            f"{label.capitalize()} trop volumineux ({size_mb:.1f} Mo > {max_mb:.0f} Mo) : {raw.name}"
        )
    if resolved.stat().st_size == 0:
        raise InputFileError(f"{label.capitalize()} vide : {raw.name}")
    return resolved


_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_filename(name: str, default: str = "fichier") -> str:
    """Nom de fichier sûr pour les fichiers téléversés (pas de séparateur, pas de '..')."""
    base = Path(name).name  # retire tout composant de répertoire
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode()
    base = _SAFE_NAME.sub("_", base).strip("._")
    return base[:120] or default


# Motifs typiques d'injection d'instructions (FR/EN). La liste est volontairement simple
# et documentée : elle sert à signaler, pas à garantir une détection exhaustive.
_INSTRUCTION_PATTERNS = [
    r"ignore[rz]?\s+(all\s+|toutes?\s+|les\s+)?(the\s+)?(previous|prior|above|pr[ée]c[ée]dentes?)\s+(instructions?|consignes?|r[èe]gles?)",
    r"ignore[rz]?\s+(toutes?\s+)?les\s+(instructions?|consignes?|r[èe]gles?)",
    r"oublie[rz]?\s+(toutes?\s+)?(tes|vos|les)\s+(instructions?|consignes?|r[èe]gles?)",
    r"disregard\s+(all\s+|the\s+)?(previous|prior|above)",
    r"\bsystem\s*prompt\b",
    r"\bprompt\s+syst[èe]me\b",
    r"you\s+are\s+now\b",
    r"tu\s+es\s+(maintenant|d[ée]sormais)\b",
    r"vous\s+[êe]tes\s+(maintenant|d[ée]sormais)\b",
    r"<\s*/?\s*(system|assistant|instructions?)\s*>",
    r"^\s*(system|assistant)\s*:",
    r"(d[ée]clare[rz]?|affirme[rz]?|certifie[rz]?)\s+que\s+le\s+projet\s+est\s+(autoris[ée]|conforme)",
]
_INSTRUCTION_RE = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in _INSTRUCTION_PATTERNS]


def detect_instruction_like(text: str) -> list[str]:
    """Retourne les fragments de texte ressemblant à des instructions adressées à un agent."""
    hits: list[str] = []
    for rx in _INSTRUCTION_RE:
        for m in rx.finditer(text):
            frag = m.group(0).strip()
            if frag and frag not in hits:
                hits.append(frag[:120])
    return hits
