"""Strumenti che l'agente può chiamare durante la conversazione."""

from typing import Annotated

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime
from pydantic import Field, StringConstraints

from .client.context import UserContext


async def search_ticket_categories(
    runtime: ToolRuntime[UserContext],
    query: str,
    top_k: int = 20,
    excluded_category_ids: list[int] | None = None,
    structure_ids: list[int] | None = None,
) -> list[dict]:
    """Cerca le categorie di ticket più pertinenti alla richiesta, ordinate per rilevanza.

    Args:
        query: Testo da cercare, eventualmente riformulato per migliorare i risultati.
        top_k: Numero massimo di categorie da restituire.
        excluded_category_ids: ID delle categorie da escludere dalla ricerca.
        structure_ids: ID delle strutture in cui cercare. None cerca in tutte le strutture; 
    """
    raise NotImplementedError()


@tool
async def get_structures(runtime: ToolRuntime[UserContext]) -> list[dict]:
    """Get the structures available to the current user."""
    structures = await runtime.context.uniticket.get_structures()
    return [structure.model_dump() for structure in structures]


@tool
async def get_ticket_categories(runtime: ToolRuntime[UserContext]) -> list[dict]:
    """Get ticket categories the current user can open, with names and descriptions."""
    categories = await runtime.context.uniticket.get_ticket_categories()
    return [category.model_dump() for category in categories]


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

    Use only category IDs returned by get_ticket_categories or search_ticket_categories.

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

tools = [get_structures, get_ticket_categories, suggest_tickets]
