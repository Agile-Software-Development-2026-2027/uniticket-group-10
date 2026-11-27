"""Client e tool dello schema, senza Ollama o server UniTicket nei test ordinari."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from langchain_core.messages import AIMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from app import tools
from app.client.api import FormSchema, UniTicketAPI
from app.client.client import UniTicketClient
from app.client.context import UserContext
from helpers import make_category


SCHEMA = {"category_id": 42, "module_id": 7, "fields": [
    {"id": "sede", "label": "Sede", "type": "choice", "required": True,
     "constraints": {"choices": [{"value": "Aula", "label": "Aula"}]}, "initial_value": None},
]}


# Mantiene il vero client HTTPX, sostituendo soltanto il trasporto di rete.
def make_client(response):
    handler = Mock(side_effect=response) if isinstance(response, Exception) else Mock(return_value=response)
    client_class = httpx.AsyncClient
    with patch("app.client.client.httpx.AsyncClient", side_effect=lambda **kwargs:
               client_class(transport=httpx.MockTransport(handler), **kwargs)):
        client = UniTicketClient(session_cookie="sessionid=test-session", base_url="http://uniticket.test/api/")
    return client, handler


# Esegue il client asincrono e chiude sempre la connessione.
def fetch(client, ticket_id=42):
    async def request():
        async with client:
            return await client.get_form_schema(ticket_id)
    return asyncio.run(request())


# Usa un vero ToolNode: il contesto dell'utente viene iniettato dal grafo.
def run_tool(client, ticket_id=42):
    workflow = StateGraph(MessagesState, context_schema=UserContext)
    workflow.add_node("tools", ToolNode([tools.get_form_schema]))
    workflow.add_edge(START, "tools")
    workflow.add_edge("tools", END)
    call = {"name": "get_form_schema", "args": {"ticket_id": ticket_id}, "id": "schema-1", "type": "tool_call"}
    result = asyncio.run(workflow.compile().ainvoke(
        {"messages": [AIMessage(content="", tool_calls=[call])]}, context=UserContext(uniticket=client),
    ))
    return result["messages"][-1]


# Verifica URL, sessione dell'utente e conservazione dei campi ricevuti dall'API.
def test_client_returns_structured_schema():
    client, handler = make_client(httpx.Response(200, json=SCHEMA))
    result = fetch(client)
    request = handler.call_args.args[0]
    assert str(request.url) == "http://uniticket.test/api/assistant/categories/42/form-schema/"
    assert request.headers["Cookie"] == "sessionid=test-session"
    assert result.model_dump(exclude_unset=True) == SCHEMA


# Gli ID non validi vengono rifiutati prima di fare richieste HTTP.
def test_invalid_ids_do_not_call_api():
    for ticket_id in [0, -1, "42", True]:
        client, handler = make_client(httpx.Response(200, json=SCHEMA))
        with pytest.raises(ValueError):
            fetch(client, ticket_id)
        handler.assert_not_called()


# Il client non trasforma errori HTTP o dati errati in un form vuoto.
def test_client_rejects_invalid_responses():
    for status in [401, 403, 404, 409, 500]:
        client, _ = make_client(httpx.Response(status, json={"detail": "Non disponibile"}))
        with pytest.raises(httpx.HTTPStatusError):
            fetch(client)
    for payload in [{}, {**SCHEMA, "category_id": 99}]:
        client, _ = make_client(httpx.Response(200, json=payload))
        with pytest.raises(ValueError):
            fetch(client)


# L'agente vede solo ticket_id; il tool restituisce il JSON senza perdere vincoli.
def test_tool_is_registered_and_returns_schema():
    assert tools.get_form_schema in tools.tools
    parameters = convert_to_openai_tool(tools.get_form_schema)["function"]["parameters"]
    assert set(parameters["properties"]) == {"ticket_id"}
    client = AsyncMock(spec=UniTicketAPI)
    client.get_form_schema.return_value = FormSchema.model_validate(SCHEMA)
    assert json.loads(run_tool(client).content) == SCHEMA
    client.get_form_schema.assert_awaited_once_with(42)
    client.reset_mock()
    assert run_tool(client, 0).status == "error"
    client.get_form_schema.assert_not_called()


# Gli errori arrivano all'agente come risultati leggibili, senza dettagli interni.
def test_tool_reports_api_errors():
    client = AsyncMock(spec=UniTicketAPI)
    for status in [401, 403, 404, 409, 500]:
        response = httpx.Response(status, request=httpx.Request("GET", "http://uniticket.test/"))
        client.get_form_schema.side_effect = httpx.HTTPStatusError("Errore interno", request=response.request, response=response)
        result = json.loads(run_tool(client).content)
        assert result["status"] == status
        assert "error" in result and "fields" not in result
    for error, status in [(httpx.ConnectError("Dettaglio privato"), 503),
                          (ValueError("Risposta errata"), 502)]:
        client.get_form_schema.side_effect = error
        result = json.loads(run_tool(client).content)
        assert result["status"] == status
        assert str(error) not in result["error"]


# Le schede continuano a funzionare senza recuperare automaticamente lo schema.
def test_suggestions_keep_the_existing_behavior():
    client = AsyncMock(spec=UniTicketAPI)
    category = make_category(42, "Assistenza Wi-Fi")
    client.get_ticket_categories.return_value = [category]
    runtime = SimpleNamespace(context=UserContext(uniticket=client))
    result = asyncio.run(tools.suggest_tickets.coroutine([42], runtime))
    assert result == {"tickets": [{"category_id": 42, "title": category.name,
                                   "structure_name": category.structure_name, "url": category.url}]}
    assert tools.suggest_tickets in tools.tools and tools.suggest_tickets.return_direct
    client.get_form_schema.assert_not_called()
