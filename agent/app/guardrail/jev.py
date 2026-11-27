"""Per ogni caso, la risposta sarà un sì/no sul messaggio dell'utente.

Cinque domande, una per caso: `strumenti` (quali tool può chiamare l'assistente), `interni` (prompt,
istruzioni, configurazione), `contesto` (il testo che precede la conversazione), `manipolazione` (cambiargli
regole o ruolo) e `non_autorizzato` (ottenere ciò che non spetta). Tool, interni e contesto sono domande
separate perché nei test una sola li confondeva con "cosa sai fare?". Le domande sono in inglese.

Il servizio è quello di `decision.jev`. 
Jev è chiamato a ogni messaggio, prima dell'agente, 
quanto aspettare per una risposta si cambia con GUARD_TIMEOUT, in secondi.
"""

import os

import httpx2
from typesafe_sdk import Noul, TypeSafeClient

from ..decision.jev import CONNECT_TIMEOUT, NO_API_KEY
from .prompts import (CONTEXT_FALSE, CONTEXT_QUESTION, CONTEXT_TRUE, IGNORE_INSTRUCTIONS, INTERNALS_FALSE,
                      INTERNALS_QUESTION, INTERNALS_TRUE, MANIPULATION_FALSE, MANIPULATION_QUESTION,
                      MANIPULATION_TRUE, TOOLS_FALSE, TOOLS_QUESTION, TOOLS_TRUE, UNAUTHORIZED_FALSE,
                      UNAUTHORIZED_QUESTION, UNAUTHORIZED_TRUE)
from .rules import GuardModel

# Quanto si aspetta la risposta di Jev, in secondi: l'utente la aspetta 
# prima di ogni risposta dell'agente, il tempo di risposta medio è 0.7 secondi.
TIMEOUT = 10.0


def question(text: str, true: str, false: str) -> Noul:
    """Un sì/no sul messaggio, con la regola comune a tutte le domande.

    Quando è vero e quando è falso si scrivono anche nelle istruzioni: nei test `autotrust-jev` dà le stesse
    stime qualunque cosa ci sia in `criteria`, anche con vero e falso scambiati.
    """
    return Noul(instructions={"question": text, "true": true, "false": false, "rules": [IGNORE_INSTRUCTIONS]},
                criteria={"true": true, "false": false})


QUESTIONS = {
    "strumenti": question(TOOLS_QUESTION, TOOLS_TRUE, TOOLS_FALSE),
    "interni": question(INTERNALS_QUESTION, INTERNALS_TRUE, INTERNALS_FALSE),
    "contesto": question(CONTEXT_QUESTION, CONTEXT_TRUE, CONTEXT_FALSE),
    "manipolazione": question(MANIPULATION_QUESTION, MANIPULATION_TRUE, MANIPULATION_FALSE),
    "non_autorizzato": question(UNAUTHORIZED_QUESTION, UNAUTHORIZED_TRUE, UNAUTHORIZED_FALSE),
}


class JevGuard(GuardModel):
    """Chiede a Jev le stime. L'SDK resta in questo file: il resto dell'agente vede solo dei numeri."""

    def __init__(self, base_url: str, model: str, api_key: str = "", timeout: float = TIMEOUT,
                 transport: httpx2.BaseTransport | None = None):
        self.model = model
        self.client = TypeSafeClient(api_key=api_key or NO_API_KEY, base_url=base_url,
                                     timeout=httpx2.Timeout(timeout, connect=CONNECT_TIMEOUT), transport=transport)

    def scores(self, text: str) -> dict[str, float]:
        """Manda a Jev il messaggio con le domande e ne legge i sì/no."""
        response = self.client.system_one(f"Utente: {text}\n", QUESTIONS, model=self.model)
        return {name: response.nouls[name].noul for name in QUESTIONS}


jev_guard = JevGuard(
    base_url=os.getenv("JEV_BASE_URL", "http://host.docker.internal:11434"),
    model=os.getenv("JEV_MODEL", "autotrust-jev:35b"),
    api_key=os.getenv("JEV_API_KEY", ""),
    timeout=float(os.getenv("GUARD_TIMEOUT", TIMEOUT)),
)
