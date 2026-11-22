"""Strumenti che l'agente può chiamare durante la conversazione."""

import json
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

@tool(parse_docstring=True)
async def search_ticket_categories(
    runtime: ToolRuntime[UserContext],
    query: str,
    structure_ids: list[int] | None = None,
    excluded_category_ids: list[int] | None = None,
) -> list[dict]:
    """Cerca le categorie di ticket più pertinenti alla richiesta, ordinate per rilevanza.

        PREREQUISITO: Usa questo tool solo DOPO aver ottenuto l'elenco delle
        strutture
        tramite `get_structures`.

        Args:
            query: Testo da cercare, eventualmente riformulato per migliorare i
            risultati.
            structure_ids: ID delle strutture rilevanti selezionati da
            `get_structures`. Usa None solo se nessuna struttura è
            compatibile.
            excluded_category_ids: ID delle categorie da escludere dalla ricerca.
    """
    categories = await runtime.context.uniticket.search_ticket_categories(
        query,
        excluded_category_ids=excluded_category_ids,
        structure_ids=structure_ids,
    )
    return [category.model_dump() for category in categories]


@tool
async def get_structures(runtime: ToolRuntime[UserContext]) -> list[dict]:
    """Get the structures available to the current user."""
    structures = await runtime.context.uniticket.get_structures()
    return [structure.model_dump() for structure in structures]


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
    # senza che l'LLM li ricopi o li scremi (misurato: g10n in misure/LEGGIMI.md).
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
    """Le categorie di cui si è chiesta conferma a chi poi ha detto di essere di un altro dipartimento.

    Non vanno riproposte: senza questo, se l'assistente ricerca senza escluderle, la stessa categoria
    torna da sola e, a conferma già chiesta, passa per la risposta giusta.
    """
    declined = []
    for index, decision in past_decisions(messages):
        if decision["action"] != "CONFIRM":
            continue
        answer = ". ".join(message.text for message in messages[index + 1:] if isinstance(message, HumanMessage))
        declined += [category["id"] for category in decision["categories"]
                     if belongs_elsewhere(category["structure_name"], answer)]
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
# get_structures e search_ticket_categories restano disponibili ma l'assistente non li riceve:
# filtrare per struttura e scegliere i candidati a mano faceva perdere il modulo giusto prima di Jev.
tools = [find_ticket_categories, get_form_schema]
