import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app import graph, tools
from app.client.api import UniTicketAPI
from app.client.context import UserContext
from helpers import FirstCandidateModel, make_category

LAUREA = make_category(2, "Certificato di laurea")
TASSE = make_category(1, "Pagamento tasse")


class ScriptedModel:
    """Un LLM finto che risponde con i messaggi dati, uno per chiamata, e annota cosa ha letto."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.seen = []

    def bind_tools(self, _tools):
        return self

    async def ainvoke(self, messages, config=None):
        self.seen.append(messages)
        return self.replies.pop(0)


def find_call(query="certificato di laurea"):
    return AIMessage(content="", tool_calls=[
        {"name": "find_ticket_categories", "args": {"query": query}, "id": "call-find", "type": "tool_call"}])


@pytest.fixture(autouse=True)
def fake_decision_model(monkeypatch):
    monkeypatch.setattr(tools, "decision_model", FirstCandidateModel())


def run(monkeypatch, model, found):
    monkeypatch.setattr(graph, "llm", model)
    client = AsyncMock(spec=UniTicketAPI)
    client.search_ticket_categories.return_value = found
    client.get_ticket_categories.return_value = [LAUREA, TASSE]
    state = asyncio.run(graph.create_graph().ainvoke(
        {"messages": [HumanMessage("mi serve il certificato di laurea")]},
        context=UserContext(uniticket=client),
    ))
    return state["messages"]


def tool_results(messages):
    return [(message.name, json.loads(message.content)) for message in messages if isinstance(message, ToolMessage)]


def test_a_proposal_shows_the_decided_cards_and_then_the_assistant_answers(monkeypatch):
    model = ScriptedModel(find_call(), AIMessage("Ecco il modulo per il certificato."))

    messages = run(monkeypatch, model, [LAUREA, TASSE])

    results = tool_results(messages)
    assert [name for name, _ in results] == ["find_ticket_categories", "suggest_tickets"]
    assert [ticket["category_id"] for ticket in results[1][1]["tickets"]] == [2]
    assert messages[-1].content == "Ecco il modulo per il certificato."
    # L'assistente scrive la risposta dopo aver visto la decisione e le card.
    assert isinstance(model.seen[-1][-1], ToolMessage)


def test_without_categories_no_cards_are_shown(monkeypatch):
    model = ScriptedModel(find_call(), AIMessage("Nel catalogo non c'è un servizio adatto."))

    messages = run(monkeypatch, model, [])

    assert [name for name, _ in tool_results(messages)] == ["find_ticket_categories"]
    assert messages[-1].content == "Nel catalogo non c'è un servizio adatto."


def test_without_a_tool_call_the_assistant_just_answers(monkeypatch):
    model = ScriptedModel(AIMessage("Ciao! Di cosa hai bisogno?"))

    messages = run(monkeypatch, model, [LAUREA])

    assert tool_results(messages) == []
    assert messages[-1].content == "Ciao! Di cosa hai bisogno?"
