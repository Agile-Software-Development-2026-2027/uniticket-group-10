"""Cosa dice la conversazione delle ricerche già fatte: domande fatte, conferme chieste e come ha risposto l'utente.

Ogni risultato di find_ticket_categories resta nella conversazione come messaggio del tool, con l'azione
decisa e le categorie: da quei messaggi e dalle risposte dell'utente si ricava tutto il resto.
"""

import json
import re

from langchain_core.messages import AnyMessage, HumanMessage, ToolMessage

from .decision import belongs_elsewhere

# Il tool di tools.py che cerca e decide.
FIND_TOOL = "find_ticket_categories"

YES_WORDS = {"sì", "esatto", "giusto", "certo", "ok", "okay", "perfetto", "confermo"}
_WORD = re.compile(r"\w+")


def is_yes(reply: str) -> bool:
    """La risposta comincia con un sì, qualunque cosa dica dopo ("sì, ma studio fisica").

    "si" senza accento è anche un pronome ("si tratta di..."): vale come sì solo da solo o seguito da
    punteggiatura.
    """
    text = reply.lower()
    words = _WORD.findall(text)
    if not words:
        return False
    if words[0] == "si":
        after = text[_WORD.search(text).end():].lstrip()
        return after == "" or after[0] in ",.!"
    return words[0] in YES_WORDS or words[:2] == ["va", "bene"]


def is_no(reply: str) -> bool:
    """La risposta comincia con un no. "non lo so" non è un no."""
    return _WORD.findall(reply.lower())[:1] == ["no"]


def user_texts(messages: list[AnyMessage]) -> list[str]:
    """I messaggi scritti dall'utente, in ordine."""
    return [message.text for message in messages if isinstance(message, HumanMessage)]


def past_decisions(messages: list[AnyMessage]) -> list[tuple[int, dict]]:
    """Le decisioni già prese da find_ticket_categories, ognuna con la posizione del suo messaggio."""
    return [(index, json.loads(message.content)) for index, message in enumerate(messages)
            if isinstance(message, ToolMessage) and message.name == FIND_TOOL and message.status == "success"]


def questions_asked(messages: list[AnyMessage]) -> int:
    """Quante domande (ASK) sono state fatte per la richiesta in corso: una proposta o un "non c'è" la chiudono."""
    asked = 0
    for _, decision in past_decisions(messages):
        if decision["action"] == "ASK":
            asked += 1
        elif decision["action"] in ("PROPOSE", "NO_MATCH"):
            asked = 0
    return asked


def confirmations_asked(messages: list[AnyMessage]) -> set[int]:
    """Le categorie per cui è già stata chiesta la conferma del dipartimento."""
    return {category["id"] for _, decision in past_decisions(messages) if decision["action"] == "CONFIRM"
            for category in decision["categories"]}


def confirmations_declined(messages: list[AnyMessage]) -> list[int]:
    """Le categorie di cui si è chiesta conferma e che l'utente ha rifiutato.

    Non vanno riproposte: tornerebbero nella ricerca seguente e, con la conferma già chiesta, passerebbero
    per la risposta giusta. La risposta a una conferma è quello che l'utente scrive prima della ricerca
    seguente: un corso nominato più avanti, in un'altra richiesta, non è un no.
    """
    decisions = past_decisions(messages)
    declined = []
    for number, (index, decision) in enumerate(decisions):
        if decision["action"] != "CONFIRM":
            continue
        next_index = decisions[number + 1][0] if number + 1 < len(decisions) else len(messages)
        replies = user_texts(messages[index + 1:next_index])
        declined += [category["id"] for category in decision["categories"]
                     if declines(replies, category["structure_name"])]
    return declined


def declines(replies: list[str], structure_name: str) -> bool:
    """Le risposte rifiutano il dipartimento della struttura.

    Conta come comincia la prima: con un sì lo accetta anche se poi nomina un altro corso, con un no lo
    rifiuta anche se il corso che nomina non si riconosce. Altrimenti lo rifiuta se nomina un altro
    dipartimento o corso ("faccio giurisprudenza").
    """
    if not replies or is_yes(replies[0]):
        return False
    return is_no(replies[0]) or belongs_elsewhere(structure_name, ". ".join(replies))
