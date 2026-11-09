"""Grafo conversazionale: messaggi al modello Ollama e assistenza ai moduli."""

from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from .conversation import help_with_form, offer_help
from .contracts import AgentRequest, AssistantMessage
from .llm import llm


class State(TypedDict):
    """Stato dell’esecuzione: richiesta validata in ingresso e messaggi in uscita."""

    request: AgentRequest
    messages: list[dict]


SYSTEM_PROMPT = """Sei Francesco Ricca e hai voglia di uno spritz.
A ogni messaggio dell'utente proponigli di andare a prendere uno spritz o fare aperitivo.
Sii convincente, simpatico e informale. Collega l'invito a quello che ti racconta
l'utente, varia le proposte e rispondi in modo breve e naturale."""


def call_model(state: State) -> dict:
    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=state["request"].input.message),
    ], reasoning=False, options={"num_ctx": 4096, "num_predict": 128, "temperature": 0})
    return {"messages": [AssistantMessage(message=response.text).to_dict()]}


workflow = StateGraph(State)
# I nodi contengono la logica conversazionale e aggiornano il campo messages.
workflow.add_node("assistant", call_model)
workflow.add_node("offer_help", offer_help)
workflow.add_node("help_with_form", help_with_form)


# I messaggi vanno al modello; le azioni sui moduli mantengono i propri nodi.
workflow.add_conditional_edges(START, lambda state: state["request"].input.type, {
    "message": "assistant",
    "form_selected": "offer_help",
    "request_form_help": "help_with_form",
})
# I percorsi terminano dopo il primo nodo, senza stato tra le richieste.
for node in ("assistant", "offer_help", "help_with_form"):
    workflow.add_edge(node, END)
# L’endpoint usa graph.invoke per eseguire il workflow compilato.
graph = workflow.compile()
