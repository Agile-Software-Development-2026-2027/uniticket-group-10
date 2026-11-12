import json

import pytest
from langchain_core.messages import AIMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from app import tools
from app.contracts import AgentRequest
from app.graph import State
from app.retrieval import Retriever
from helpers import KeywordEmbedder, make_category


@pytest.fixture(autouse=True)
def fake_retriever(monkeypatch):
    """Sostituisce il retriever di bge-m3 con uno finto: i test non hanno bisogno di Ollama."""
    monkeypatch.setattr(tools, "retriever", Retriever(KeywordEmbedder()))


def make_request(catalog):
    return AgentRequest(input={"type": "message", "message": "ciao"}, catalog=catalog)


def test_the_model_sees_only_the_search_parameters():
    parameters = convert_to_openai_tool(tools.search_ticket_categories)["function"]["parameters"]

    assert set(parameters["properties"]) == {"query", "top_k", "exclude", "structure_ids"}
    assert parameters["required"] == ["query"]


def test_the_tool_returns_the_candidates_from_the_most_relevant():
    request = make_request([make_category(1, "Pagamento tasse"), make_category(2, "Certificato di laurea")])

    results = tools.search_ticket_categories.invoke({"query": "certificato di laurea", "request": request})

    assert results == [
        {"id": 2, "name": "Certificato di laurea", "description": "", "structure_id": 1, "structure_name": ""},
        {"id": 1, "name": "Pagamento tasse", "description": "", "structure_id": 1, "structure_name": ""},
    ]


def test_the_tool_applies_top_k_exclude_and_structure_ids():
    request = make_request([make_category(1, "Certificato di laurea", structure_id=10),
                            make_category(2, "Laurea e tasse", structure_id=10),
                            make_category(3, "Laurea magistrale", structure_id=20)])

    results = tools.search_ticket_categories.invoke(
        {"query": "laurea", "request": request, "top_k": 1, "exclude": [1], "structure_ids": [10]})

    assert [candidate["id"] for candidate in results] == [2]


def test_the_agent_calls_the_tool_with_the_catalog_of_the_request():
    workflow = StateGraph(State)
    workflow.add_node("tools", ToolNode([tools.search_ticket_categories]))
    workflow.add_edge(START, "tools")
    workflow.add_edge("tools", END)
    request = make_request([make_category(1, "Pagamento tasse"), make_category(2, "Certificato di laurea")])
    call = {"name": "search_ticket_categories", "args": {"query": "laurea", "top_k": 1},
            "id": "call-1", "type": "tool_call"}

    state = workflow.compile().invoke({"request": request, "messages": [AIMessage(content="", tool_calls=[call])]})

    assert [candidate["id"] for candidate in json.loads(state["messages"][-1].content)] == [2]
