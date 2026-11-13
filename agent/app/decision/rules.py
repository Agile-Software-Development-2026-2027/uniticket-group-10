"""Decisione sui candidati della ricerca: il modello stima, il codice decide.

Un modello (Jev) dice quanto è probabile ogni ipotesi: ciascuna categoria candidata,
"nessuna va bene" e "l'utente ha detto troppo poco". Una regola fissa trasforma poi
la stima in una decisione: si prova senza modello e si capisce perché ha deciso così.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Literal

from ..contracts import Category

# Quota che le ipotesi più probabili devono raggiungere insieme.
CONFIDENCE = 0.8


class Hypothesis(Enum):
    """Le due ipotesi che non sono una categoria: distinte anche dall'azione "NO_MATCH" di una decisione."""

    NO_MATCH = auto()  # nessuna categoria va bene
    NEEDS_INFO = auto()  # l'utente ha detto troppo poco


@dataclass
class Estimate:
    """La stima del modello: le quote di tutte le ipotesi sommano a 1."""

    categories: list[tuple[Category, float]] = field(default_factory=list)
    no_match: float = 0.0
    needs_info: float = 0.0


class DecisionModel(ABC):
    """L'interfaccia comune dei modelli: Jev oggi, un altro domani, senza toccare il resto."""

    max_candidates: int  # quanti candidati accetta al massimo

    @abstractmethod
    def estimate(self, query: str, candidates: list[Category]) -> Estimate:
        """Quanto è probabile ogni candidato, che nessuno vada bene e che l'utente abbia detto troppo poco."""


def likely_hypotheses(estimate: Estimate, confidence: float = CONFIDENCE) -> list[Category | Hypothesis]:
    """Le ipotesi più probabili, prese dalla prima finché insieme non raggiungono la confidenza."""
    hypotheses = [*estimate.categories, (Hypothesis.NO_MATCH, estimate.no_match),
                  (Hypothesis.NEEDS_INFO, estimate.needs_info)]
    hypotheses.sort(key=lambda hypothesis: hypothesis[1], reverse=True)
    likely, total = [], 0.0
    for hypothesis, share in hypotheses:
        if total >= confidence or share <= 0:
            break
        likely.append(hypothesis)
        total += share
    return likely


@dataclass
class Decision:
    """Cosa fare e con quali categorie, dalla più probabile."""

    action: Literal["PROPOSE", "ASK", "NO_MATCH"]
    categories: list[Category] = field(default_factory=list)


def decide(estimate: Estimate, confidence: float = CONFIDENCE, max_options: int = 5) -> Decision:
    """Propone se le ipotesi più probabili sono solo poche categorie, altrimenti chiede o dice che non c'è.

    `max_options` è quante categorie si mostrano al massimo all'utente.
    """
    likely = likely_hypotheses(estimate, confidence)
    categories = [hypothesis for hypothesis in likely if isinstance(hypothesis, Category)]
    if likely == [Hypothesis.NO_MATCH]:
        return Decision("NO_MATCH")
    only_categories = len(categories) == len(likely)
    if categories and only_categories and len(categories) <= max_options:
        return Decision("PROPOSE", categories)
    return Decision("ASK", categories[:max_options])


def decide_with(model: DecisionModel, query: str, candidates: list[Category]) -> Decision:
    """La decisione di un modello sui candidati: riceve solo i primi in classifica, quanti ne accetta."""
    asked = candidates[:model.max_candidates]
    return decide(model.estimate(query, asked))
