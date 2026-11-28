"""Strumenti che l'agente può chiamare durante la conversazione."""

from asyncio import to_thread
from typing import Annotated, Any

import httpx
from pydantic import Field
from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime

from .client.context import ConversationContext
from .decision import decide_with
from .decision.jev import jev

decision_model = jev


@tool(parse_docstring=True)
async def search_ticket_categories(
    runtime: ToolRuntime[ConversationContext],
    query: str,
    structure_ids: list[int] | None = None,
    excluded_category_ids: list[int] | None = None,
) -> list[dict]:
    """Cerca le categorie di ticket più pertinenti alla richiesta, ordinate per rilevanza.

        PREREQUISITO: Usa questo tool solo DOPO aver ottenuto l'elenco delle
        strutture
        tramite `get_available_structures`.

        Args:
            query: Testo da cercare, eventualmente riformulato per migliorare i
            risultati.
            structure_ids: ID delle strutture rilevanti selezionati da
            `get_available_structures`. Usa None solo se nessuna struttura è
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
async def get_structures(runtime: ToolRuntime[ConversationContext]) -> list[dict]:
    """Get the structures available to the current user."""
    structures = await runtime.context.uniticket.get_structures()
    return [structure.model_dump() for structure in structures]


# Recupera il modulo della categoria scelta e restituisce i dati che l'agente può leggere.
@tool(parse_docstring=True)
async def get_form_schema(
    ticket_id: Annotated[int, Field(gt=0, strict=True)],
    runtime: ToolRuntime[ConversationContext],
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
async def decide_ticket_categories(
    query: str,
    candidate_ids: list[int],
    runtime: ToolRuntime[ConversationContext],
) -> dict:
    """Decide se proporre le categorie, chiedere chiarimenti o non proporne nessuna.

    Args:
        query: La richiesta dell'utente con le sue parole, completa di quello che ha detto nei messaggi precedenti.
        candidate_ids: ID delle categorie candidate, ordinate per rilevanza.
    """
    catalog = await runtime.context.uniticket.get_ticket_categories()
    available = {category.id: category for category in catalog}
    candidates = [available[category_id] for category_id in candidate_ids if category_id in available]
    decision = await to_thread(decide_with, decision_model, query, candidates)
    return {
        "action": decision.action,
        "categories": [
            category.model_dump(include={"id", "name", "description", "structure_id", "structure_name"})
            for category in decision.categories
        ],
    }


@tool(return_direct=True)
async def suggest_tickets(
    ticket_ids: list[int],
    runtime: ToolRuntime[ConversationContext],
) -> dict:
    """Display selected ticket categories as clickable cards.

    Use only category IDs returned by search_ticket_categories.

    This tool completes the assistant's response.

    Ticket titles, structures, and URLs are loaded from
    the authorized catalog.
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


@tool(parse_docstring=True)
async def set_field(
    field_id: str | int,
    value: Any,
    runtime: ToolRuntime[UserContext],
) -> dict[str, Any]:
    """Aggiorna il valore di un campo nel form del ticket attualmente aperto senza inviare il ticket.

    Usa solo gli identificativi dei campi appartenenti al form aperto.

    Args:
        field_id: Identificativo del campo da aggiornare nel form aperto.
        value: Valore da assegnare al campo.
    """
    normalized_field_id = str(field_id)
    category_id = runtime.context.category_id

    if category_id is None:
        return {
            "ok": False,
            "field_id": normalized_field_id,
            "error": "Nessun form ticket è attualmente aperto.",
        }

    try:
        schema = await runtime.context.uniticket.get_form_schema(category_id)
    except ValueError as exc:
        return {
            "ok": False,
            "field_id": normalized_field_id,
            "error": str(exc),
        }
    except httpx.HTTPStatusError as exc:
        return {
            "ok": False,
            "field_id": normalized_field_id,
            "error": f"Impossibile leggere lo schema del form (HTTP {exc.response.status_code}).",
        }
    except httpx.HTTPError as exc:
        return {
            "ok": False,
            "field_id": normalized_field_id,
            "error": f"Errore di comunicazione con UniTicket: {exc}",
        }

    editable_fields = {f.id: f for f in schema.fields if not f.disabled}
    if normalized_field_id not in editable_fields:
        return {
            "ok": False,
            "field_id": normalized_field_id,
            "error": (
                f"Il campo '{normalized_field_id}' non appartiene ai campi modificabili "
                f"del form aperto (categoria {category_id})."
            ),
            "available_fields": [
                {"id": f.id, "label": f.label, "type": f.type, "required": f.required}
                for f in editable_fields.values()
            ],
        }

    runtime.context.form_fields[normalized_field_id] = value

    return {
        "ok": True,
        "category_id": category_id,
        "field_id": normalized_field_id,
        "value": value,
    }


triage_tools = [get_structures, search_ticket_categories, get_form_schema, suggest_tickets]
form_filler_tools = [get_form_schema, set_field]
tools = [get_structures, search_ticket_categories, get_form_schema, suggest_tickets, set_field]