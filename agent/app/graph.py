"""Grafo LangGraph che esegue una singola richiesta della conversazione.

Un messaggio utente avvia la ricerca dei ticket; form_selected propone aiuto e
request_form_help avvia l'assistenza. Ogni richiesta attraversa un nodo e
termina restituendo i messaggi prodotti, senza conservare stato tra le POST.
"""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from .conversation import help_with_form, offer_help, search_tickets
from .contracts import AgentRequest


class State(TypedDict):
    """Stato dell’esecuzione: richiesta validata in ingresso e messaggi in uscita."""

    request: AgentRequest
    messages: list[dict]


workflow = StateGraph(State)
# I nodi contengono la logica conversazionale e aggiornano il campo messages.
workflow.add_node("search_tickets", search_tickets)
workflow.add_node("offer_help", offer_help)
workflow.add_node("help_with_form", help_with_form)


# Il tipo di input determina il percorso, senza una decisione affidata a un LLM.
workflow.add_conditional_edges(START, lambda state: state["request"].input.type, {
    "message": "search_tickets",
    "form_selected": "offer_help",
    "request_form_help": "help_with_form",
})
# I percorsi terminano dopo il primo nodo, senza stato tra le richieste.
for node in ("search_tickets", "offer_help", "help_with_form"):
    workflow.add_edge(node, END)
# L’endpoint usa graph.invoke per eseguire il workflow compilato.
graph = workflow.compile()
