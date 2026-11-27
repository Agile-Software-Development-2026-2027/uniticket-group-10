"""Jev, il modello di decisione: non scrive testo, risponde con probabilità a domande tipizzate.

Riceve la richiesta dell'utente e tre tipi di domanda:
- `vago`, un sì/no: l'utente ha detto troppo poco;
- `modulo`, una scelta tra i candidati: quale categoria gli serve;
- `adatto_M1`, `adatto_M2`..., un sì/no per candidato: quella categoria gli serve davvero.
Una scelta sceglie comunque qualcosa, i sì/no possono risultare tutti bassi: per questo servono entrambi.
Le domande sono in inglese, la lingua in cui Jev rende meglio; i dati restano in italiano.

Lo stesso servizio (`POST /v1/systemone`) è offerto da TypeSafe AI e da `autotrust-jev` in Ollama:
si sceglie con JEV_BASE_URL, JEV_MODEL e, solo per TypeSafe, JEV_API_KEY. Lo si chiama con l'SDK di
TypeSafe, che vale per entrambi; l'SDK resta in questo file: il resto dell'agente vede solo una stima.
Quanto aspettare la risposta si sceglie con JEV_TIMEOUT, in secondi.
"""

import os

import httpx2
from typesafe_sdk import Choice, ChoiceAnswer, Noul, NoulAnswer, Question, TypeSafeClient

from ..client.api import Catalog
from .cards import card
from .prompts import (FITS_FALSE, FITS_QUESTION, FITS_TRUE, FORM_QUESTION, FORM_RULES, VAGUE_FALSE,
                      VAGUE_QUESTION, VAGUE_TRUE)
from .rules import DecisionModel, Estimate

# Come si legge un sì/no di Jev: da 0,7 in su è sì, fino a 0,3 è no.
NOUL_YES = 0.7
NOUL_NO = 0.3
# Per "adatto" il no comincia più in basso: un "adatto" tiepido lascia una quota alle categorie.
FITS_NO = 0.1
# Conta l'"adatto" delle prime 3 della scelta: alto su una categoria scartata non conta.
CHECKED_FORMS = 3
# L'SDK vuole sempre una chiave; Ollama non la chiede e la ignora.
NO_API_KEY = "ollama"
# Quanto si aspetta la risposta di Jev, in secondi: deve restare tempo all'LLM entro i 150 del proxy Django.
TIMEOUT = 60.0
# Un server che non accetta nemmeno la connessione è spento: non serve aspettarlo quanto una risposta.
CONNECT_TIMEOUT = 5.0


def code(index: int) -> str:
    """I candidati si chiamano M1, M2...: codici brevi, uguali in tutte le domande."""
    return f"M{index + 1}"


def yes_no(instructions: dict, true: str, false: str) -> Noul:
    """Un sì/no con scritto quando è vero e quando è falso.

    Vero e falso si scrivono anche nelle istruzioni: `autotrust-jev` in Ollama non legge `criteria` e dà le
    stesse stime anche con vero e falso scambiati. TypeSafe li legge, per questo restano anche in `criteria`.
    """
    return Noul(instructions=instructions | {"true": true, "false": false}, criteria={"true": true, "false": false})


def build_questions(candidates: list[Catalog]) -> dict[str, Question]:
    """Le domande per Jev: se la richiesta è vaga e, per i candidati, quale serve e se serve davvero."""
    questions: dict[str, Question] = {"vago": yes_no({"question": VAGUE_QUESTION}, VAGUE_TRUE, VAGUE_FALSE)}
    if not candidates:  # l'API rifiuta una scelta senza opzioni
        return questions
    options = {}
    for index, category in enumerate(candidates):
        options[code(index)] = card(category, with_structure=True)
        # Se è adatta non dipende dalla struttura: qui Jev legge la categoria senza.
        fits = {"question": FITS_QUESTION, "modulo": card(category)}
        questions[f"adatto_{code(index)}"] = yes_no(fits, FITS_TRUE, FITS_FALSE)
    if len(options) > 1:  # l'API rifiuta una scelta con una sola opzione: con un candidato basta il suo "adatto"
        questions["modulo"] = Choice(instructions={"question": FORM_QUESTION, "rules": FORM_RULES},
                                     criteria=options)
    return questions


def ramp(noul: float, no: float) -> float:
    """Porta un sì/no di Jev tra 0 e 1: fino a `no` vale 0, da NOUL_YES vale 1, in mezzo sale in linea retta."""
    return min(1.0, max(0.0, (noul - no) / (NOUL_YES - no)))


def parse_answers(nouls: dict[str, NoulAnswer], choices: dict[str, ChoiceAnswer],
                  candidates: list[Catalog]) -> Estimate:
    """Ricompone le risposte di Jev, divise dall'SDK in sì/no e scelte, in una stima.

    servono informazioni = vago
    nessuna categoria    = (1 - vago) × (1 - adatto)
    categoria i          = (1 - vago) × adatto × P(i)
    """
    vague = ramp(nouls["vago"].noul, NOUL_NO)
    if not candidates:
        return Estimate(no_match=1 - vague, needs_info=vague)
    by_code = {code(index): category for index, category in enumerate(candidates)}
    # Con un solo candidato la scelta non si chiede (vedi build_questions): è lui con probabilità 1.
    given = choices["modulo"].probabilities if len(candidates) > 1 else {code(0): 1.0}
    probabilities = {key: given[key] for key in by_code if given.get(key, 0) > 0}
    if not probabilities:
        raise ValueError("Jev non ha dato probabilità ai candidati")
    ranked = sorted(probabilities, key=probabilities.get, reverse=True)
    fits = ramp(max(nouls[f"adatto_{key}"].noul for key in ranked[:CHECKED_FORMS]), FITS_NO)
    total = sum(probabilities.values())  # arrivano arrotondate: si riportano a somma 1
    categories = [(by_code[key], (1 - vague) * fits * probabilities[key] / total) for key in ranked]
    return Estimate(categories, no_match=(1 - vague) * (1 - fits), needs_info=vague)


class JevModel(DecisionModel):
    """Chiede la stima a Jev. `max_candidates` è quante opzioni accetta: 16 per `autotrust-jev`."""

    def __init__(self, base_url: str, model: str, max_candidates: int, api_key: str = "",
                 timeout: float = TIMEOUT, transport: httpx2.BaseTransport | None = None):
        self.model = model
        self.max_candidates = max_candidates
        self.client = TypeSafeClient(api_key=api_key or NO_API_KEY, base_url=base_url,
                                     timeout=httpx2.Timeout(timeout, connect=CONNECT_TIMEOUT), transport=transport)

    def estimate(self, query: str, candidates: list[Catalog]) -> Estimate:
        """Manda a Jev la richiesta e le domande sui candidati, e ne legge le risposte."""
        response = self.client.system_one(f"Utente: {query}\n", build_questions(candidates), model=self.model)
        return parse_answers(response.nouls, response.choices, candidates)


jev = JevModel(
    base_url=os.getenv("JEV_BASE_URL", "http://host.docker.internal:11434"),
    model=os.getenv("JEV_MODEL", "autotrust-jev:35b"),
    max_candidates=int(os.getenv("JEV_MAX_CANDIDATES", "16")),
    api_key=os.getenv("JEV_API_KEY", ""),
    timeout=float(os.getenv("JEV_TIMEOUT", TIMEOUT)),
)
