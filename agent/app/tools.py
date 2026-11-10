"""Strumenti che l'agente può chiamare durante la conversazione."""

from typing import Annotated

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from .contracts import AgentRequest
from .embeddings import embedder
from .retrieval import Retriever

DEFAULT_TOP_K = 20
# Quello che serve per scegliere tra i candidati: URL e visibilità restano nel catalogo.
CANDIDATE_FIELDS = {"id", "name", "description", "structure_id", "structure_name"}

retriever = Retriever(embedder)


@tool(parse_docstring=True)
def search_ticket_categories(
    query: str,
    request: Annotated[AgentRequest, InjectedState("request")],
    top_k: int = DEFAULT_TOP_K,
    exclude: list[int] | None = None,
    structure_ids: list[int] | None = None,
) -> list[dict]:
    """Cerca le categorie di ticket più adatte alla richiesta dell'utente, dalla più rilevante.

    Args:
        query: La richiesta dell'utente, con le sue parole.
        top_k: Quante categorie restituire al massimo.
        exclude: ID delle categorie da non restituire, per esempio quelle che l'utente ha già scartato.
        structure_ids: ID delle strutture a cui limitare la ricerca. Senza, si cerca in tutte.
    """
    categories = retriever.search(query, request.catalog, top_k, exclude, structure_ids)
    return [category.model_dump(include=CANDIDATE_FIELDS) for category in categories]
