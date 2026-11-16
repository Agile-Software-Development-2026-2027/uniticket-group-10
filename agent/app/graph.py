"""Grafo condiviso da FastAPI e test: messaggi e tool LangChain standard."""
from langchain.agents import create_agent

from .client.context import UserContext
from .tools import tools

from .llm import llm

SYSTEM_PROMPT = """Sei l'assistente UniTicket. Aiuta l'utente a trovare il servizio
adatto e a capire come presentare una richiesta. Non inventare i campi del modulo. Non inventare servizi, permessi o URL.
Se la richiesta è ambigua, chiedi un chiarimento. Non puoi creare ticket.
Rispondi in modo breve e chiaro nella lingua usata dall’utente."""

def create_graph(checkpointer=None):
    return create_agent(
        model=llm,
        tools=tools,
        #context_schema=UserContext, # Non funziona se lo metto, la documentazione lo richiede... ma non spiega perché...
        system_prompt=SYSTEM_PROMPT,
        checkpointer=checkpointer,
    )
