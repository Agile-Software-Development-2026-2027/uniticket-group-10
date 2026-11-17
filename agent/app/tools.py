"""Strumenti che l'agente può chiamare durante la conversazione."""

from asyncio import to_thread
from typing import Annotated

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime
from pydantic import Field, StringConstraints

from .client.context import UserContext
from .decision import decide_with
from .decision.jev import jev

decision_model = jev

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
async def get_structures(runtime: ToolRuntime[UserContext]) -> list[dict]:
    """Get the structures available to the current user."""
    structures = await runtime.context.uniticket.get_structures()
    return [structure.model_dump() for structure in structures]


@tool(parse_docstring=True)
async def decide_ticket_categories(
    query: str,
    candidate_ids: list[int],
    runtime: ToolRuntime[UserContext],
) -> dict:
    """Decide se proporre le categorie, chiedere chiarimenti o non proporne nessuna.

    Args:
        query: La richiesta dell'utente, con le sue parole.
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
    message: Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=200,
    ),
    Field(
        description=(
            "A short, plain-text introduction in the user's language. "
            "Prefer one sentence, ideally under 100 characters. "
            "Do not use Markdown."
        )
    )],
    runtime: ToolRuntime[UserContext],
) -> dict:
    """Display selected ticket categories as clickable cards.

    Use only category IDs returned by search_ticket_categories.

    Generate a short introduction in the user's language.
    The message MUST be plain text without Markdown formatting.

    The message will be displayed alongside the ticket cards.
    This tool completes the assistant's response.

    Ticket titles, structures, and URLs are loaded from
    the authorized catalog.
    """
    categories = {category.id: category for category in await runtime.context.uniticket.get_ticket_categories()}
    return {"message": message, "tickets": [
        {
            "category_id": categories[ticket_id].id,
            "title": categories[ticket_id].name,
            "structure_name": categories[ticket_id].structure_name,
            "url": categories[ticket_id].url,
        }
        for ticket_id in ticket_ids if ticket_id in categories
    ]}

tools = [get_structures, search_ticket_categories, suggest_tickets]
