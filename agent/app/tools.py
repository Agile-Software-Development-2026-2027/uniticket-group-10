"""Strumenti che l'agente può chiamare durante la conversazione."""

from typing import Annotated

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from .contracts import AgentRequest
from .decision import decide_with
from .embeddings import embedder
from .jev import jev
from .retrieval import Retriever

DEFAULT_TOP_K = 20
# Quello che serve per scegliere tra i candidati: URL e visibilità restano nel catalogo.
CANDIDATE_FIELDS = {"id", "name", "description", "structure_id", "structure_name"}

retriever = Retriever(embedder)
# Il modello che decide sui candidati: per usarne un altro basta cambiare questa riga.
decision_model = jev


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


@tool(parse_docstring=True)
def decide_ticket_categories(
    query: str,
    candidate_ids: list[int],
    request: Annotated[AgentRequest, InjectedState("request")],
) -> dict:
    """Decide cosa fare con le categorie candidate: proporle, chiedere un chiarimento o dire che nessuna va bene.

    Args:
        query: La richiesta dell'utente, con le sue parole.
        candidate_ids: ID delle categorie trovate da search_ticket_categories, nello stesso ordine.
    """
    # I candidati si rileggono dal catalogo: il modello non può proporre categorie inventate o nascoste.
    visible = {category.id: category for category in request.catalog if not category.hidden}
    candidates = [visible[candidate_id] for candidate_id in candidate_ids if candidate_id in visible]
    decision = decide_with(decision_model, query, candidates)
    return {
        "action": decision.action,
        "categories": [category.model_dump(include=CANDIDATE_FIELDS) for category in decision.categories],
    }
