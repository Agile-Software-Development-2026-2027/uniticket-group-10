"""Strumenti che l'agente può chiamare durante la conversazione."""

import json
import re
from asyncio import to_thread
from typing import Annotated

import httpx
from pydantic import Field
from langchain_core.messages import AnyMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime

from .client.context import UserContext
from .decision import belongs_elsewhere, confirm_department, decide_with, departments, stop_asking
from .decision.jev import jev

decision_model = jev
# Quello che l'assistente legge di una categoria decisa: URL e visibilità restano nel catalogo.
CANDIDATE_FIELDS = {"id", "name", "description", "structure_id", "structure_name"}
# Una risposta che comincia con un sì accetta il dipartimento, qualunque cosa dica dopo: si è chiesto se è
# quello che gli serve, non se ne fa parte. "si" senza accento è anche un pronome ("si tratta di..."):
# vale come sì solo da solo o seguito da punteggiatura.
_YES = re.compile(r"^\W*(?:(?:sì|esatto|giusto|certo|ok|okay|perfetto|confermo|va bene)(?!\w)|si(?=\s*(?:[,.!]|$)))",
                  re.IGNORECASE)
# Una risposta che comincia con un no lo rifiuta, anche se il corso che nomina non si riconosce
# ("no, ho fatto chimica"). Solo la parola intera: "non lo so" non è un no.
_NO = re.compile(r"^\W*no\b", re.IGNORECASE)


# Recupera il modulo della categoria scelta e restituisce i dati che l'agente può leggere.
@tool(parse_docstring=True)
async def get_form_schema(
    ticket_id: Annotated[int, Field(gt=0, strict=True)],
    runtime: ToolRuntime[UserContext],
) -> dict:
    """Legge campi, obbligatorietà e regole del modulo senza compilare o creare richieste.

    Usare questo tool quando servono i campi di una categoria individuata dalla ricerca.
    I permessi sono verificati dall'API.

    Args:
        ticket_id: ID della TicketCategory scelta, non di una richiesta compilata.
    """
    try:
        schema = await runtime.context.uniticket.get_form_schema(ticket_id)
        # Conserva anche vincoli e colonne delle tabelle, senza aggiungere valori assenti.
        return schema.model_dump(exclude_unset=True)
    except httpx.HTTPStatusError as error:
        return {"error": "Schema non disponibile per questa categoria o sessione.",
                "status": error.response.status_code}
    except httpx.RequestError:
        return {"error": "Servizio UniTicket non raggiungibile.", "status": 503}
    except ValueError:
        return {"error": "La risposta dello schema non è valida.", "status": 502}


@tool(parse_docstring=True)
async def find_ticket_categories(
    query: str,
    runtime: ToolRuntime[UserContext],
    excluded_category_ids: list[int] | None = None,
) -> dict:
    """Cerca nel catalogo le categorie adatte alla richiesta e decide cosa farne: proporle, chiedere un chiarimento o dire che nessuna va bene.

    Args:
        query: La richiesta dell'utente con le sue parole, completa di quello che ha detto nei messaggi precedenti.
        excluded_category_ids: ID delle categorie da non considerare, per esempio quelle che l'utente ha già scartato.
    """
    # Ricerca e decisione in un passo solo: i candidati vanno a Jev così come li ordina la ricerca,
    # senza che l'LLM li ricopi o li scremi: scremandoli a mano perdeva il modulo giusto prima di Jev.
    messages = (runtime.state or {}).get("messages", [])
    excluded = [*(excluded_category_ids or []), *confirmations_declined(messages)]
    candidates = await runtime.context.uniticket.search_ticket_categories(
        query, excluded_category_ids=excluded or None)
    decision = await to_thread(decide_with, decision_model, query, candidates)
    # Una sola categoria di un dipartimento che l'utente non ha nominato diventa una conferma da chiedere:
    # si guardano le parole dell'utente, non la query, in cui l'assistente potrebbe averlo dedotto.
    said = ". ".join(message.text for message in messages if isinstance(message, HumanMessage))
    decision = confirm_department(decision, said, confirmations_asked(messages))
    # Dopo una domanda non se ne fa un'altra se resta più probabile che non ci sia nulla.
    decision = stop_asking(decision, questions_asked(messages))
    result = {
        "action": decision.action,
        "categories": [category.model_dump(include=CANDIDATE_FIELDS) for category in decision.categories],
    }
    if decision.action == "CONFIRM":
        result.update(departments.describe(decision.categories[0].structure_name))
    return result


def past_decisions(messages: list[AnyMessage]) -> list[tuple[int, dict]]:
    """Le decisioni già prese da find_ticket_categories in questa conversazione, con la posizione del messaggio."""
    return [(index, json.loads(message.content)) for index, message in enumerate(messages)
            if isinstance(message, ToolMessage) and message.name == find_ticket_categories.name
            and message.status == "success"]


def confirmations_asked(messages: list[AnyMessage]) -> set[int]:
    """Le categorie per cui in questa conversazione è già stata chiesta la conferma del dipartimento."""
    return {category["id"] for _, decision in past_decisions(messages) if decision["action"] == "CONFIRM"
            for category in decision["categories"]}


def confirmations_declined(messages: list[AnyMessage]) -> list[int]:
    """Le categorie di cui si è chiesta conferma a chi poi ha detto di no o ha nominato un altro dipartimento o corso.

    Non vanno riproposte: senza questo, se l'assistente ricerca senza escluderle, la stessa categoria
    torna da sola e, a conferma già chiesta, passa per la risposta giusta. La risposta alla conferma è
    quello che l'utente scrive prima della ricerca seguente: un corso nominato dopo, in un'altra
    richiesta, non è un no. Se comincia con un sì, non è un no nemmeno se nomina un altro corso; se
    comincia con un no, lo è anche se il corso che nomina non si riconosce.
    """
    decisions = past_decisions(messages)
    declined = []
    for (index, decision), (next_index, _) in zip(decisions, [*decisions[1:], (len(messages), None)]):
        replies = [message.text for message in messages[index + 1:next_index] if isinstance(message, HumanMessage)]
        if decision["action"] != "CONFIRM" or (replies and _YES.match(replies[0])):
            continue
        refused = bool(replies) and bool(_NO.match(replies[0]))
        declined += [category["id"] for category in decision["categories"]
                     if refused or belongs_elsewhere(category["structure_name"], ". ".join(replies))]
    return declined


def questions_asked(messages: list[AnyMessage]) -> int:
    """Quante domande (ASK) sono state fatte per la richiesta in corso: una proposta o un "non c'è" la chiudono."""
    asked = 0
    for _, decision in past_decisions(messages):
        if decision["action"] == "ASK":
            asked += 1
        elif decision["action"] in ("PROPOSE", "NO_MATCH"):
            asked = 0
    return asked


@tool
async def suggest_tickets(
    ticket_ids: list[int],
    runtime: ToolRuntime[UserContext],
) -> dict:
    """Display selected ticket categories as clickable cards.

    The graph calls it with the categories decided by find_ticket_categories:
    the assistant never calls it. Ticket titles, structures, and URLs are loaded
    from the authorized catalog.
    """
    categories = {category.id: category for category in await runtime.context.uniticket.get_ticket_categories()}
    return {"tickets": [
        {
            "category_id": categories[ticket_id].id,
            "title": categories[ticket_id].name,
            "structure_name": categories[ticket_id].structure_name,
            "url": categories[ticket_id].url,
        }
        for ticket_id in ticket_ids if ticket_id in categories
    ]}

# I tool che l'assistente può chiamare: suggest_tickets lo chiama il grafo quando ci sono card da mostrare.
tools = [find_ticket_categories, get_form_schema]
