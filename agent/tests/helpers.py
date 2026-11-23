"""Dati e modelli finti condivisi dai test."""

from app.client.api import Catalog
from app.decision import DecisionModel, Estimate


def make_category(category_id, name="", structure_id=1, description="", structure_name="", audience=None,
                  field_labels=()):
    return Catalog(id=category_id, name=name or f"Categoria {category_id}", structure_id=structure_id,
                    url=f"/tickets/{category_id}", description=description,
                    structure_name=structure_name, audience=audience or {}, field_labels=list(field_labels))


def ids(categories):
    return [category.id for category in categories]


class FirstCandidateModel(DecisionModel):
    """Modello finto: è sicuro che serva il primo candidato che riceve; senza candidati, che non ci sia."""

    def __init__(self, max_candidates=16):
        self.max_candidates = max_candidates
        self.received = []

    def estimate(self, query, candidates):
        self.received = candidates
        if not candidates:
            return Estimate(no_match=1.0)
        return Estimate(categories=[(candidates[0], 1.0)])
