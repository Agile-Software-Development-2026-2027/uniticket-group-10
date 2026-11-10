"""Grafo condiviso da FastAPI e test: messaggi e tool LangChain standard."""

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, MessagesState, StateGraph
from typing import TypedDict
from .contracts import AgentRequest

from .llm import llm

SYSTEM_PROMPT = """Sei l'assistente UniTicket. Aiuta l'utente a trovare il servizio
adatto e a capire come presentare una richiesta. Non inventare i campi del modulo.
Non hai accesso al catalogo: non inventare servizi, permessi o URL.
Se la richiesta è ambigua, chiedi un chiarimento. Non puoi creare ticket.
Rispondi in modo breve e chiaro nella lingua usata dall’utente."""

class State(TypedDict):
    """Stato dell’esecuzione: richiesta validata in ingresso e messaggi in uscita."""

    request: AgentRequest
    messages: list[dict]

async def call_model(state: MessagesState, config: RunnableConfig):
    messages = state["messages"]
    latest = next((message for message in reversed(messages) if isinstance(message, HumanMessage)), None)
    if latest is None or not latest.text.strip() or len(latest.text) > 500:
        raise ValueError("Expected a user message of 1–500 characters")
    response = await llm.ainvoke([SystemMessage(content=SYSTEM_PROMPT), *messages], config=config)
    return {"messages": [response]}


workflow = StateGraph(MessagesState)
workflow.add_node("assistant", call_model)
workflow.add_edge(START, "assistant")
workflow.add_edge("assistant", END)
# FastAPI compila lo stesso workflow con un checkpointer per sessione.
graph = workflow.compile().with_config({"recursion_limit": 12})
