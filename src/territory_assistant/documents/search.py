"""Recherche lexicale BM25 sur les passages chargés (déterministe, sans modèle externe).

Choix : BM25 plutôt que des embeddings pour garder des résultats reproductibles,
explicables (termes correspondants listés) et sans téléchargement de modèle.
Limite connue : pas de synonymie ; « crue » ne retrouve pas « inondation » sauf si
les deux termes figurent dans la requête.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

from territory_assistant.documents.loader import Chunk, LoadedDocument

STOPWORDS = {
    "les",
    "des",
    "une",
    "dans",
    "pour",
    "par",
    "sur",
    "avec",
    "est",
    "sont",
    "que",
    "qui",
    "quoi",
    "quel",
    "quels",
    "quelle",
    "quelles",
    "aux",
    "ces",
    "cette",
    "ceux",
    "cet",
    "elle",
    "ils",
    "leur",
    "leurs",
    "pas",
    "plus",
    "etre",
    "doit",
    "doivent",
    "peut",
    "peuvent",
    "son",
    "ses",
    "tout",
    "tous",
    "toute",
    "toutes",
    "entre",
    "lors",
    "ainsi",
    "afin",
    "avant",
    "apres",
    "sans",
    "sous",
    "comme",
    "mais",
    "donc",
    "ou",
    "et",
    "du",
    "de",
    "la",
    "le",
    "un",
    "the",
    "and",
    "for",
    "with",
    "this",
    "that",
    "zone",  # « zone » : trop générique ici
}


def normalize(text: str) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t)


def stem(token: str) -> str:
    """Racinisation minimale : retire le pluriel en -s / -x des mots longs."""
    if len(token) > 4 and token[-1] in "sx":
        return token[:-1]
    return token


def tokenize(text: str) -> list[str]:
    return [stem(t) for t in normalize(text).split() if len(t) >= 3 and t not in STOPWORDS]


@dataclass
class SearchHit:
    document: LoadedDocument
    chunk: Chunk
    score: float
    matched_terms: list[str]
    excerpt: str
    truncated: bool


def _excerpt(text: str, terms: set[str], max_chars: int = 420) -> tuple[str, bool]:
    """Extrait court et VERBATIM (sous-chaîne exacte du passage) autour des termes trouvés."""
    if len(text) <= max_chars:
        return text, False
    sentences = [(m.start(), m.group(0)) for m in re.finditer(r"[^.!?]+[.!?]?", text)]
    best_start, best_hits = 0, -1
    for start, sent in sentences:
        hits = len(set(tokenize(sent)) & terms)
        if hits > best_hits:
            best_start, best_hits = start, hits
    while best_start < len(text) and text[best_start] == " ":
        best_start += 1
    end = min(len(text), best_start + max_chars)
    if end < len(text):
        cut = text.rfind(" ", best_start, end)
        end = cut if cut > best_start else end
    return text[best_start:end], (best_start > 0 or end < len(text))


class BM25Index:
    """Index BM25 en mémoire sur tous les passages de tous les documents."""

    def __init__(self, documents: list[LoadedDocument], k1: float = 1.5, b: float = 0.75) -> None:
        self.items: list[tuple[LoadedDocument, Chunk, Counter]] = []
        for doc in documents:
            for ch in doc.chunks:
                self.items.append((doc, ch, Counter(tokenize(f"{ch.section or ''} {ch.text}"))))
        self.k1, self.b = k1, b
        self.n = len(self.items)
        self.avgdl = (sum(sum(c.values()) for *_, c in self.items) / self.n) if self.n else 0.0
        df: Counter = Counter()
        for *_, c in self.items:
            df.update(set(c))
        self.idf = {t: math.log(1 + (self.n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def search(self, query_terms: list[str], *, top_k: int, min_score: float) -> list[SearchHit]:
        q = []
        for term in query_terms:
            q.extend(tokenize(term))
        q_set = set(q)
        hits: list[SearchHit] = []
        for doc, ch, tf in self.items:
            dl = sum(tf.values()) or 1
            score, matched = 0.0, []
            for t in q_set:
                if t in tf:
                    f = tf[t]
                    score += (
                        self.idf.get(t, 0.0)
                        * f
                        * (self.k1 + 1)
                        / (f + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1)))
                    )
                    matched.append(t)
            if score >= min_score and matched:
                excerpt, truncated = _excerpt(ch.text, set(matched))
                hits.append(
                    SearchHit(doc, ch, round(score, 3), sorted(matched), excerpt, truncated)
                )
        hits.sort(key=lambda h: (-h.score, h.chunk.chunk_id))
        return hits[:top_k]
