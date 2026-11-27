import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from app import tools
from app.client.api import UniTicketAPI
from app.client.context import UserContext, ConversationContext
from helpers import FirstCandidateModel, make_category


@pytest.fixture(autouse=True)
def fake_decision_model(monkeypatch):
    """Sostituisce Jev con un modello finto: i test non hanno bisogno del server."""
    model = FirstCandidateModel()
    monkeypatch.setattr(tools, "decision_model", model)
    return model


@pytest.fixture
def decision_graph():
    workflow = StateGraph(MessagesState, context_schema=ConversationContext)
    workflow.add_node("tools", ToolNode([tools.decide_ticket_categories]))
    workflow.add_edge(START, "tools")
    workflow.add_edge("tools", END)
    return workflow.compile()


def run_decision(graph, catalog, candidate_ids):
    client = AsyncMock(spec=UniTicketAPI)
    client.get_ticket_categories.return_value = catalog
    call = {
        "name": "decide_ticket_categories",
        "args": {"query": "certificato di laurea", "candidate_ids": candidate_ids},
        "id": "call-1", "type": "tool_call",
    }
    state = asyncio.run(graph.ainvoke(
        {"messages": [AIMessage(content="", tool_calls=[call])]},
        context=ConversationContext(
                uniticket=client,
                user=UserContext(
                    first_name="Ciccio",
                    last_name="Pasticcio",
                    email="ciccio.pasticcio@unical.it",
                    identifier=676767,
                    is_employee=True,
                ),
                selected_form=0,
            )
    ))
    return json.loads(state["messages"][-1].content)


def test_the_model_sees_only_the_decision_parameters():
    parameters = convert_to_openai_tool(tools.decide_ticket_categories)["function"]["parameters"]

    assert set(parameters["properties"]) == {"query", "candidate_ids"}
    assert parameters["required"] == ["query", "candidate_ids"]


def test_the_decision_tool_returns_the_action_and_the_categories(decision_graph):
    catalog = [make_category(1, "Pagamento tasse"), make_category(2, "Certificato di laurea")]

    decision = run_decision(decision_graph, catalog, [2, 1])

    assert decision == {"action": "PROPOSE", "categories": [
        {"id": 2, "name": "Certificato di laurea", "description": "", "structure_id": 1, "structure_name": ""},
    ]}


def test_the_decision_tool_ignores_ids_outside_the_authorized_catalog(decision_graph, fake_decision_model):
    catalog = [make_category(1), make_category(2)]

    run_decision(decision_graph, catalog, [99, 2, 1])

    assert fake_decision_model.received == [catalog[1], catalog[0]]


def test_the_decision_tool_reports_no_match_without_candidates(decision_graph):
    decision = run_decision(decision_graph, [make_category(1)], [])

    assert decision == {"action": "NO_MATCH", "categories": []}


def test_the_agent_uses_the_catalog_from_each_run_context(decision_graph):
    first = run_decision(decision_graph, [make_category(1)], [2, 1])
    second = run_decision(decision_graph, [make_category(2)], [2, 1])

    assert [category["id"] for category in first["categories"]] == [1]
    assert [category["id"] for category in second["categories"]] == [2]
