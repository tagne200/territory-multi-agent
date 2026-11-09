"""Découpage des documents (.md, .txt, .pdf) en passages traçables.

Chaque passage garde : identifiant, section (titre Markdown) ou page (PDF), texte exact.
Les passages contenant du texte ressemblant à des instructions sont marqués
`suspicious_hits` : ils restent des données, ne sont jamais exécutés et ne sont pas
transmis au LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from territory_assistant.errors import DataReadError
from territory_assistant.safety import detect_instruction_like

MAX_CHUNK_CHARS = 1200
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass
class Chunk:
    chunk_id: str
    text: str
    section: str | None = None
    page: int | None = None
    suspicious_hits: list[str] = field(default_factory=list)


@dataclass
class LoadedDocument:
    source_id: str
    filename: str
    title: str
    chunks: list[Chunk]
    warnings: list[str] = field(default_factory=list)


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _split_long(text: str) -> list[str]:
    """Coupe un paragraphe trop long aux fins de phrase."""
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]
    parts, current = [], ""
    for sentence in re.split(r"(?<=[.!?;])\s+", text):
        if current and len(current) + len(sentence) + 1 > MAX_CHUNK_CHARS:
            parts.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        parts.append(current)
    # garde-fou si une « phrase » dépasse seule la limite
    return [p[i : i + MAX_CHUNK_CHARS] for p in parts for i in range(0, len(p), MAX_CHUNK_CHARS)]


def _paragraphs(block: str) -> list[str]:
    return [_normalize_ws(p) for p in re.split(r"\n\s*\n", block) if _normalize_ws(p)]


def _decode(path: Path) -> str:
    raw = path.read_bytes()
    if b"\x00" in raw[:4096]:
        raise DataReadError(f"{path.name} semble binaire : document texte attendu.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DataReadError(f"{path.name} n'est pas encodé en UTF-8.") from exc
    return _CTRL_RE.sub(" ", text)


def _chunks_markdown(text: str, prefix: str) -> tuple[str | None, list[Chunk]]:
    title, section, buf, chunks = None, None, [], []

    def flush() -> None:
        for para in _paragraphs("\n".join(buf)):
            for piece in _split_long(para):
                chunks.append(
                    Chunk(chunk_id=f"{prefix}#{len(chunks) + 1}", text=piece, section=section)
                )
        buf.clear()

    for line in text.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            flush()
            section = m.group(2).strip()
            if title is None and len(m.group(1)) == 1:
                title = section
        else:
            buf.append(line)
    flush()
    return title, chunks


def _chunks_text(text: str, prefix: str) -> tuple[str | None, list[Chunk]]:
    chunks: list[Chunk] = []
    for para in _paragraphs(text):
        for piece in _split_long(para):
            chunks.append(Chunk(chunk_id=f"{prefix}#{len(chunks) + 1}", text=piece))
    first = text.strip().splitlines()[0].strip() if text.strip() else None
    return (first[:150] if first else None), chunks


def _chunks_pdf(path: Path, prefix: str) -> tuple[str | None, list[Chunk], list[str]]:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    warnings: list[str] = []
    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            raise DataReadError(f"{path.name} est chiffré : non lisible par le prototype.")
        chunks: list[Chunk] = []
        empty_pages = 0
        for page_no, page in enumerate(reader.pages, start=1):
            text = _CTRL_RE.sub(" ", page.extract_text() or "")
            paras = _paragraphs(text) or ([_normalize_ws(text)] if text.strip() else [])
            if not paras:
                empty_pages += 1
            for para in paras:
                for piece in _split_long(para):
                    chunks.append(
                        Chunk(chunk_id=f"{prefix}#{len(chunks) + 1}", text=piece, page=page_no)
                    )
        if empty_pages:
            warnings.append(
                f"{path.name} : {empty_pages} page(s) sans texte extractible (PDF scanné ? OCR non géré)."
            )
        title = (reader.metadata.title if reader.metadata else None) or None
        return title, chunks, warnings
    except DataReadError:
        raise
    except (PdfReadError, ValueError, KeyError, OSError) as exc:
        raise DataReadError(f"PDF malformé ({path.name}) : {type(exc).__name__}") from exc


def load_document(
    path: Path, *, source_id: str, display_name: str, title_hint: str | None
) -> LoadedDocument:
    """Charge un document et retourne ses passages. Lève DataReadError si illisible."""
    ext = path.suffix.lower()
    warnings: list[str] = []
    try:
        if ext == ".pdf":
            title, chunks, warnings = _chunks_pdf(path, source_id)
        elif ext == ".md":
            title, chunks = _chunks_markdown(_decode(path), source_id)
        elif ext == ".txt":
            title, chunks = _chunks_text(_decode(path), source_id)
        else:
            raise DataReadError(f"Format de document non géré : {ext}")
    except OSError as exc:
        raise DataReadError(f"Lecture impossible de {path.name} : {exc}") from exc

    if not chunks:
        warnings.append(f"{path.name} : aucun texte exploitable.")
    for ch in chunks:
        ch.suspicious_hits = detect_instruction_like(ch.text)
    n_susp = sum(1 for c in chunks if c.suspicious_hits)
    if n_susp:
        warnings.append(
            f"{path.name} : {n_susp} passage(s) contiennent du texte ressemblant à des instructions "
            "adressées à un agent. Ils sont traités comme des données, signalés et exclus du LLM."
        )
    return LoadedDocument(
        source_id=source_id,
        filename=display_name,
        title=title_hint or title or path.stem,
        chunks=chunks,
        warnings=warnings,
    )
