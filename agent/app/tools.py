"""Strumenti che l'agente può chiamare durante la conversazione."""

from asyncio import to_thread
from typing import Annotated

import httpx
from pydantic import Field
from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime

from .client.api import Catalog
from .client.context import UserContext
from .conversation import confirmations_asked, confirmations_declined, questions_asked, user_texts
from .decision import confirm_department, decide_with, departments, stop_asking
from .decision.jev import jev

decision_model = jev
# Quello che l'assistente legge di una categoria decisa: URL e visibilità restano nel catalogo.
CANDIDATE_FIELDS = {"id", "name", "description", "structure_id", "structure_name"}

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
    # I candidati vanno a Jev nell'ordine della ricerca, senza passare dall'LLM.
    messages = (runtime.state or {}).get("messages", [])
    excluded = [*(excluded_category_ids or []), *confirmations_declined(messages)]
    candidates = await runtime.context.uniticket.search_ticket_categories(
        query, excluded_category_ids=excluded or None)
    decision = await to_thread(decide_with, decision_model, query, candidates)
    # Il dipartimento si cerca nelle parole dell'utente, non nella query, dove l'assistente potrebbe averlo dedotto.
    said = ". ".join(user_texts(messages))
    decision = confirm_department(decision, said, confirmations_asked(messages))
    decision = stop_asking(decision, questions_asked(messages))
    result = {
        "action": decision.action,
        "categories": [candidate(category) for category in decision.categories],
    }
    if decision.action == "CONFIRM":
        result.update(departments.describe(decision.categories[0].structure_name))
    return result


def candidate(category: Catalog) -> dict:
    """Una categoria decisa per l'assistente: di un dipartimento anche il nome esteso, perché non indovini la sigla."""
    result = category.model_dump(include=CANDIDATE_FIELDS)
    if departments.is_department(category.structure_name):
        result["department"] = departments.label(category.structure_name)
    return result


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
