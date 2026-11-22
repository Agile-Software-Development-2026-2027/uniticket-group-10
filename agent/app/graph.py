"""Grafo dell'agente: l'assistente conversa e, quando serve, cerca; le card le mostra il grafo.

L'assistente (un LLM) decide a ogni giro se rispondere all'utente o chiamare find_ticket_categories,
che cerca le categorie e fa decidere Jev cosa farne. Se la decisione porta delle categorie, il grafo
chiama suggest_tickets con quelle (le card non dipendono da cosa ricopia l'LLM); poi l'assistente
scrive la risposta seguendo l'azione decisa.

    START → assistant ─┬─ (nessun tool) → END
                       └─ tools(find) ─┬─ categorie → propose → tools(suggest) → assistant
                                       └─ nessuna   → assistant
"""
import json
from typing import Literal
from uuid import uuid4

from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from .llm import llm
from .tools import find_ticket_categories, suggest_tickets, tools

SYSTEM_PROMPT = """Sei l'assistente UniTicket. Aiuta l'utente a trovare il servizio
adatto e a capire come presentare una richiesta. Non inventare i campi del modulo. Non inventare servizi, permessi o URL.
Non puoi creare ticket. Rispondi in modo breve e chiaro nella lingua usata dall’utente.

Prima di cercare nel catalogo, guarda se l'utente ha detto di cosa ha bisogno.
- Se non l'ha detto (un saluto, "ho un problema", "mi serve aiuto"), non chiamare nessun tool:
  rispondi e fagli una sola domanda per capirlo.
- Se l'ha detto, anche in più messaggi, chiama find_ticket_categories.
  La `query` riassume con le parole dell'utente tutto quello che ha chiesto nella conversazione,
  non solo l'ultimo messaggio.

Poi segui l'azione che find_ticket_categories restituisce:
- PROPOSE: le categorie restituite vengono mostrate all'utente come card da aprire.
  Non ripeterne l'elenco: scrivi una o due frasi e, se sono più d'una, di' in cosa differiscono
  o chiedi quale gli serve.
- CONFIRM: la categoria restituita è riservata a un dipartimento che l'utente non ha nominato; la sua
  card viene mostrata comunque. Non presentarla come la risposta: di' che è riservata a chi fa parte di
  `department`, per esempio a chi studia uno dei `courses`, e chiedi se ne fa parte. Se risponde di sì,
  digli di aprire la card. Se risponde di no, o dice il suo corso o dipartimento, chiama di nuovo
  find_ticket_categories aggiungendo alla `query` il corso o il dipartimento che ha detto.
- ASK: fai una sola domanda che aiuti a scegliere tra le categorie restituite, che vengono mostrate
  come card anche in questo caso: l'utente può aprirne una, quindi non ripeterne l'elenco. Se non ce
  ne sono, chiedi all'utente di spiegare meglio cosa gli serve.
- NO_MATCH: di' che nel catalogo non c'è un servizio adatto alla richiesta.
Se l'utente dice che le categorie mostrate non sono quelle giuste, chiama di nuovo find_ticket_categories
con i loro ID in `excluded_category_ids`.

Nomina solo le categorie restituite da find_ticket_categories: non inventare servizi, permessi o URL."""


async def call_model(state: MessagesState, config: RunnableConfig) -> dict:
    """L'assistente risponde o chiama find_ticket_categories."""
    model = llm.bind_tools(tools)
    response = await model.ainvoke([SystemMessage(content=SYSTEM_PROMPT), *state["messages"]], config=config)
    return {"messages": [response]}


def after_tools(state: MessagesState) -> Literal["propose", "assistant"]:
    """Se la decisione porta delle categorie se ne mostrano le card; altrimenti si torna dall'assistente.

    Vale anche per una domanda (ASK): l'utente che riconosce la sua richiesta tra le card la apre subito.
    """
    last = state["messages"][-1]
    decided = last.name == find_ticket_categories.name and last.status == "success"
    return "propose" if decided and json.loads(last.content)["categories"] else "assistant"


def propose(state: MessagesState) -> dict:
    """Chiama suggest_tickets con le categorie decise: la chiamata si costruisce qui, non la scrive l'LLM."""
    ticket_ids = [category["id"] for category in json.loads(state["messages"][-1].content)["categories"]]
    call = {"name": suggest_tickets.name, "args": {"ticket_ids": ticket_ids}, "id": f"call_{uuid4().hex}",
            "type": "tool_call"}
    return {"messages": [AIMessage(content="", tool_calls=[call])]}


def create_graph(checkpointer=None):
    # Niente context_schema=UserContext: l'adapter AG-UI ne genera lo schema JSON e fallisce sul campo
    # UniTicketAPI. Il contesto arriva comunque ai tool da UniTicketAgent.for_request().
    workflow = StateGraph(MessagesState)
    workflow.add_node("assistant", call_model)
    workflow.add_node("tools", ToolNode([*tools, suggest_tickets]))
    workflow.add_node("propose", propose)
    workflow.add_edge(START, "assistant")
    # Se l'assistente ha chiamato un tool si va ai tool, altrimenti si finisce.
    workflow.add_conditional_edges("assistant", tools_condition)
    workflow.add_conditional_edges("tools", after_tools)
    workflow.add_edge("propose", "tools")
    return workflow.compile(checkpointer=checkpointer)
