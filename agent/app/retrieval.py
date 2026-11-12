"""Ricerca delle categorie di ticket più adatte alla richiesta dell'utente.

Django manda soltanto le categorie attive, non scadute e accessibili all'utente:
qui si scartano quelle nascoste e quelle che l'agente chiede di escludere, poi
si ordinano le rimaste per somiglianza di significato con la richiesta.
"""

import math

from langchain_core.embeddings import Embeddings

from .contracts import Category


def filter_categories(catalog: list[Category], exclude: list[int] | None = None,
                      structure_ids: list[int] | None = None) -> list[Category]:
    """Le categorie proponibili: visibili, non escluse e, se indicate, delle strutture scelte."""
    excluded = set(exclude or [])
    structures = set(structure_ids or [])
    return [
        category for category in catalog
        if not category.hidden
        and category.id not in excluded
        and (not structures or category.structure_id in structures)
    ]


def category_text(category: Category) -> str:
    """Il testo della categoria per l'embedding: corto, perché il senso del servizio non si diluisca."""
    text = category.name
    if category.description:
        text += f". {category.description}"
    if category.structure_name:
        text += f". Struttura: {category.structure_name}"
    return text


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Quanto due vettori puntano nella stessa direzione: 1 se uguale, 0 se non hanno nulla in comune."""
    dot = sum(x * y for x, y in zip(a, b))
    norms = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norms if norms else 0.0


class Retriever:
    """Classifica le categorie per somiglianza con la richiesta, con un embedder intercambiabile."""

    def __init__(self, embedder: Embeddings):
        self.embedder = embedder
        self.vectors: dict[str, list[float]] = {}

    def search(self, query: str, catalog: list[Category], top_k: int,
               exclude: list[int] | None = None, structure_ids: list[int] | None = None) -> list[Category]:
        """Le top_k categorie più vicine alla richiesta, scelte tra quelle che passano i filtri."""
        if top_k < 1:
            raise ValueError(f"top_k deve essere almeno 1, non {top_k}")
        candidates = filter_categories(catalog, exclude, structure_ids)
        if not candidates:
            return []
        self._embed_missing(candidates)
        query_vector = self.embedder.embed_query(query)
        ranked = sorted(
            candidates,
            key=lambda category: cosine_similarity(query_vector, self.vectors[category_text(category)]),
            reverse=True,
        )
        return ranked[:top_k]

    def _embed_missing(self, categories: list[Category]) -> None:
        """Calcola i vettori delle sole categorie mai viste e li tiene in memoria per le richieste successive."""
        missing = list({category_text(category) for category in categories} - self.vectors.keys())
        if missing:
            self.vectors.update(zip(missing, self.embedder.embed_documents(missing)))
