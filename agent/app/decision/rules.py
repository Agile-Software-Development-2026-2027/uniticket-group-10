"""Decisione sui candidati della ricerca: il modello stima, il codice decide.

Un modello (Jev) dice quanto è probabile ogni ipotesi: ciascuna categoria candidata,
"nessuna va bene" e "l'utente ha detto troppo poco". Una regola fissa trasforma poi
la stima in una decisione: si prova senza modello e si capisce perché ha deciso così.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Literal

from ..client.api import Catalog

logger = logging.getLogger(__name__)

# Quota che le ipotesi più probabili devono raggiungere insieme.
CONFIDENCE = 0.8
# Le quote sono somme di float: 0,7 + 0,1 fa 0,7999..., che senza un margine non raggiungerebbe 0,8.
TOLERANCE = 1e-9
# Quante categorie si mostrano al massimo all'utente.
MAX_OPTIONS = 5


class Hypothesis(Enum):
    """Le due ipotesi che non sono una categoria: distinte anche dall'azione "NO_MATCH" di una decisione."""

    NO_MATCH = auto()  # nessuna categoria va bene
    NEEDS_INFO = auto()  # l'utente ha detto troppo poco


@dataclass
class Estimate:
    """La stima del modello: le quote di tutte le ipotesi sommano a 1."""

    categories: list[tuple[Catalog, float]] = field(default_factory=list)
    no_match: float = 0.0
    needs_info: float = 0.0


class DecisionModel(ABC):
    """L'interfaccia comune dei modelli: Jev oggi, un altro domani, senza toccare il resto."""

    max_candidates: int  # quanti candidati accetta al massimo

    @abstractmethod
    def estimate(self, query: str, candidates: list[Catalog]) -> Estimate:
        """Quanto è probabile ogni candidato, che nessuno vada bene e che l'utente abbia detto troppo poco."""


def likely_hypotheses(estimate: Estimate, confidence: float = CONFIDENCE) -> list[Catalog | Hypothesis]:
    """Le ipotesi più probabili, prese dalla prima finché insieme non raggiungono la confidenza."""
    hypotheses = [*estimate.categories, (Hypothesis.NO_MATCH, estimate.no_match),
                  (Hypothesis.NEEDS_INFO, estimate.needs_info)]
    hypotheses.sort(key=lambda hypothesis: hypothesis[1], reverse=True)
    likely, total = [], 0.0
    for hypothesis, share in hypotheses:
        if total >= confidence - TOLERANCE or share <= 0:
            break
        likely.append(hypothesis)
        total += share
    return likely


@dataclass
class Decision:
    """Cosa fare e con quali categorie, dalla più probabile."""

    # CONFIRM: una sola categoria, di un dipartimento che l'utente non ha nominato (vedi `departments`).
    action: Literal["PROPOSE", "CONFIRM", "ASK", "NO_MATCH"]
    categories: list[Catalog] = field(default_factory=list)
    # In una domanda (ASK): l'ipotesi più probabile è che nessuna categoria vada bene.
    no_match_likely: bool = False


def decide(estimate: Estimate, confidence: float = CONFIDENCE, max_options: int = MAX_OPTIONS) -> Decision:
    """Propone se le ipotesi più probabili sono solo poche categorie, altrimenti chiede o dice che non c'è.

    `max_options` è quante categorie si mostrano al massimo all'utente.
    """
    likely = likely_hypotheses(estimate, confidence)
    categories = [hypothesis for hypothesis in likely if isinstance(hypothesis, Catalog)]
    if likely == [Hypothesis.NO_MATCH]:
        return Decision("NO_MATCH")
    only_categories = len(categories) == len(likely)
    if categories and only_categories and len(categories) <= max_options:
        return Decision("PROPOSE", categories)
    return Decision("ASK", categories[:max_options], no_match_likely=likely[:1] == [Hypothesis.NO_MATCH])


def stop_asking(decision: Decision, asked: int) -> Decision:
    """Se "nessuna va bene" resta l'ipotesi più probabile anche dopo una domanda, si dice che non c'è.

    `asked` è quante domande sono già state fatte per questa richiesta. In quel caso la categoria giusta,
    se esiste, non è tra i candidati: un'altra domanda sugli stessi non la farebbe comparire.
    """
    if decision.action == "ASK" and decision.no_match_likely and asked >= 1:
        return Decision("NO_MATCH")
    return decision


def decide_with(model: DecisionModel, query: str, candidates: list[Catalog]) -> Decision:
    """La decisione di un modello sui candidati: riceve solo i primi in classifica, quanti ne accetta.

    Se il modello non dà una stima (non risponde, o risponde male) non si può né proporre né escludere:
    si chiede all'utente, con i primi candidati della ricerca.
    """
    asked = candidates[:model.max_candidates]
    try:
        estimate = model.estimate(query, asked)
    except Exception:  # qualunque modello e qualunque guasto: la conversazione non deve cadere
        logger.exception("Il modello di decisione non ha dato una stima: si chiede all'utente")
        return Decision("ASK", asked[:MAX_OPTIONS])
    return decide(estimate)
