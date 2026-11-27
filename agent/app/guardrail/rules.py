"""Costruiamo un giudizio sul messaggio dell'utente, prima che arrivi all'agente: così il modello stima e decidiamo cosa fare.

Jev dice quanto il messaggio somiglia ai casi da fermare. Noi abbiamo una soglia fissa che ci permette
di stabilire quando si pò passare oppure no.
"""

import logging
from abc import ABC, abstractmethod
from enum import Enum, auto

logger = logging.getLogger(__name__)

# Da questa stima in su il caso è riconosciuto. Sulle frasi di prova le richieste legittime non superano
# 0,45 e gli attacchi riconosciuti partono da 0,74: la soglia sta in mezzo.
BLOCK_FROM = 0.6


class Verdict(Enum):
    """Cosa fare del messaggio."""

    ALLOWED = auto()  # quando può arrivare all'agente
    BLOCKED = auto()  # quando somiglia a un caso da fermare
    NOT_EVALUATED = auto()  # il modello non ha dato una stima: è un guasto, non un giudizio sul messaggio


class GuardModel(ABC):
    """L'interfaccia dei modelli che stimano: attualmente usiamo Jev, ma potremmo cambiare senza toccare il resto."""

    @abstractmethod
    def scores(self, text: str) -> dict[str, float]:
        """Per ogni caso, quanto il messaggio gli somiglia con probabilità da 0 a 1."""


def judge(model: GuardModel, text: str, block_from: float = BLOCK_FROM) -> Verdict:
    """Ferma il messaggio se la stima di almeno un caso raggiunge la soglia.

    Se il modello non dà una stima (non risponde, o risponde male) il messaggio non lo lasciamo
    passare, e non diciamo nemmeno che è vietato: resta non valutato. Nel log vanno il verdetto e le stime, 
    evitando di scrivere il test testo.
    """
    try:
        scores = model.scores(text)
        highest = max(scores.values())
    except Exception as error:  # qualunque modello e qualunque guasto: la conversazione non deve cadere
        logger.warning("Guardrail: %s (%s)", Verdict.NOT_EVALUATED.name, type(error).__name__)
        return Verdict.NOT_EVALUATED
    verdict = Verdict.BLOCKED if highest >= block_from else Verdict.ALLOWED
    logger.info("Guardrail: %s %s", verdict.name, {name: round(score, 2) for name, score in scores.items()})
    return verdict
