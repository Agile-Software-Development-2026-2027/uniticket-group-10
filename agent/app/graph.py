"""Grafo condiviso da FastAPI e test: routing tra agente di triage e sub-agente form-filler."""

from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import SystemMessage
from langgraph.graph import END, START, MessagesState, StateGraph

from .client.context import ConversationContext

from .llm import llm
from .tools import form_filler_tools, triage_tools

TRIAGE_SYSTEM_PROMPT = """Sei l'assistente UniTicket. Aiuta l'utente a trovare il servizio
adatto e a capire come presentare una richiesta. Non inventare i campi del modulo. Non inventare servizi, permessi o URL.
Se la richiesta è ambigua, chiedi un chiarimento. Non puoi creare ticket.
Rispondi in modo breve e chiaro nella lingua usata dall’utente."""

FORM_FILLER_SYSTEM_PROMPT = """Sei l'assistente UniTicket dedicato alla compilazione del modulo aperto.
Prima di modificare un campo, usa `get_form_schema` passando il `category_id` del modulo aperto
per verificare gli identificativi (`id`), le etichette (`label`), i vincoli e le opzioni (`choices`).
Determina quali campi corrispondono alle informazioni fornite dall'utente e usa `set_field`
per aggiornarli. Compila solo i campi appartenenti al modulo attualmente aperto, non inventare
valori non richiesti e non inviare mai il ticket.
Rispondi in modo breve e chiaro nella lingua usata dall’utente."""


class UniTicketState(MessagesState):
    category_id: int | None = None
    form_fields: dict[str, Any] = {}


def route_to_agent(state: UniTicketState) -> str:
    category_id = state.get("category_id")
    if category_id is not None and not isinstance(category_id, bool) and category_id != "":
        return "form_filler_agent"
    return "triage_agent"


def create_graph(checkpointer=None):
    triage_agent = create_agent(
        model=llm,
        tools=triage_tools,
        system_prompt=TRIAGE_SYSTEM_PROMPT,
    )
    form_filler_agent = create_agent(
        model=llm,
        tools=form_filler_tools,
        system_prompt=FORM_FILLER_SYSTEM_PROMPT,
    )

    async def form_filler_node(state: UniTicketState):
        category_id = state.get("category_id")
        form_fields = state.get("form_fields") or {}

        context_msg = SystemMessage(
            content=(
                f"Modulo attualmente aperto: category_id={category_id}. "
                f"Valori già compilati (form_fields): {form_fields}."
            )
        )
        result = await form_filler_agent.ainvoke(
            {"messages": [context_msg, *state["messages"]]}
        )
        new_messages = result["messages"][len(state["messages"]) + 1 :]
        return {"messages": new_messages}

    workflow = StateGraph(
        UniTicketState,
        # Same problem as before...
        #context_schema=ConversationContext
        )
    workflow.add_node("triage_agent", triage_agent)
    workflow.add_node("form_filler_agent", form_filler_node)

    workflow.add_conditional_edges(
        START,
        route_to_agent,
        {
            "triage_agent": "triage_agent",
            "form_filler_agent": "form_filler_agent",
        },
    )
    workflow.add_edge("triage_agent", END)
    workflow.add_edge("form_filler_agent", END)

    return workflow.compile(checkpointer=checkpointer)