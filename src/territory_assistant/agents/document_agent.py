"""Agent 3 — Recherche documentaire (déterministe, documents locaux uniquement).

Contrat (en lieu et place d'un prompt système) :
- ne cherche QUE dans les documents fournis au prototype ;
- retourne des extraits courts et VERBATIM, avec fichier, section/page, identifiant de source ;
- signale les passages ressemblant à des instructions (traités comme données, exclus du LLM) ;
- si rien de pertinent n'est trouvé, le dit explicitement.
La requête est construite à partir de la question, du type de projet, des thèmes des
couches ayant produit des constats et des libellés des entités concernées.
"""

from __future__ import annotations

from territory_assistant.agents.base import RunContext
from territory_assistant.config import THEME_KEYWORDS
from territory_assistant.documents.loader import LoadedDocument, load_document
from territory_assistant.documents.search import BM25Index, tokenize
from territory_assistant.errors import TerritoryAssistantError
from territory_assistant.models import (
    DocumentEvidence,
    DocumentSearchResult,
    ScopingResult,
    SpatialAnalysisResult,
)

NO_RESULT = (
    "Aucun passage pertinent n'a été trouvé dans les documents fournis. "
    "Aucune référence documentaire n'est donc citée."
)


def build_query_terms(
    scoping: ScopingResult, spatial: SpatialAnalysisResult, question: str
) -> list[str]:
    terms: list[str] = [question]
    if scoping.project_type and scoping.project_type != "non précisé":
        terms.append(scoping.project_type)
    themes = {f.theme for f in spatial.findings}
    for theme in sorted(themes):
        terms.extend(THEME_KEYWORDS.get(theme, []))
    for f in spatial.findings:
        if f.feature_label:
            terms.append(f.feature_label)
    # dédoublonnage en conservant l'ordre
    seen, out = set(), []
    for t in terms:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


class DocumentAgent:
    name = "Agent 3 — Recherche documentaire"

    def run(
        self, ctx: RunContext, scoping: ScopingResult, spatial: SpatialAnalysisResult
    ) -> DocumentSearchResult:
        s, reg = ctx.settings, ctx.registry
        warnings: list[str] = []
        docs: list[LoadedDocument] = []
        for item in ctx.inventory.documents:
            if item.error or item.path is None:
                continue
            try:
                doc = load_document(
                    item.path,
                    source_id=item.source_id or "",
                    display_name=item.display,
                    title_hint=item.meta.name if item.meta else None,
                )
            except TerritoryAssistantError as exc:
                warnings.append(str(exc))
                if item.source_id:
                    reg.add_warning(item.source_id, str(exc))
                continue
            reg.add_processing(
                doc.source_id, f"découpage en {len(doc.chunks)} passage(s) et indexation BM25"
            )
            for w in doc.warnings:
                warnings.append(w)
                reg.add_warning(doc.source_id, w)
            docs.append(doc)

        ctx.artifacts["documents"] = {d.source_id: d for d in docs}
        query = build_query_terms(scoping, spatial, ctx.inventory.question)
        index = BM25Index(docs)
        hits = index.search(query, top_k=s.doc_top_k, min_score=s.doc_min_score) if docs else []

        evidence: list[DocumentEvidence] = []
        theme_tokens = {th: set(tokenize(" ".join(kws))) for th, kws in THEME_KEYWORDS.items()}
        for n, h in enumerate(hits, start=1):
            matched = set(h.matched_terms)
            related = sorted(th for th, toks in theme_tokens.items() if toks & matched)
            evidence.append(
                DocumentEvidence(
                    evidence_id=f"D-{n:03d}",
                    source_id=h.document.source_id,
                    filename=h.document.filename,
                    title=h.document.title,
                    section=h.chunk.section,
                    page=h.chunk.page,
                    chunk_id=h.chunk.chunk_id,
                    excerpt=h.excerpt,
                    excerpt_truncated=h.truncated,
                    score=h.score,
                    matched_terms=h.matched_terms,
                    related_themes=related,
                    suspicious_instructions=bool(h.chunk.suspicious_hits),
                )
            )
            reg.add_processing(h.document.source_id, "recherche lexicale : extrait(s) retenu(s)")

        return DocumentSearchResult(
            query_terms=sorted({t for q in query for t in tokenize(q)}),
            documents_loaded=len(docs),
            chunks_indexed=index.n,
            evidence=evidence,
            no_result_message=None if evidence else NO_RESULT,
            warnings=warnings,
        )
