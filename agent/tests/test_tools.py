import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from app import conversation, tools
from app.client.api import UniTicketAPI
from app.client.context import UserContext
from app.decision import Estimate
from helpers import FirstCandidateModel, make_category


@pytest.fixture(autouse=True)
def fake_decision_model(monkeypatch):
    """Sostituisce Jev con un modello finto: i test non hanno bisogno del server."""
    model = FirstCandidateModel()
    monkeypatch.setattr(tools, "decision_model", model)
    return model


@pytest.fixture
def find_graph():
    workflow = StateGraph(MessagesState, context_schema=UserContext)
    workflow.add_node("tools", ToolNode([tools.find_ticket_categories]))
    workflow.add_edge(START, "tools")
    workflow.add_edge("tools", END)
    return workflow.compile()


def run_find(graph, found, excluded=None, history=()):
    client = AsyncMock(spec=UniTicketAPI)
    client.search_ticket_categories.return_value = found
    args = {"query": "certificato di laurea"}
    if excluded is not None:
        args["excluded_category_ids"] = excluded
    call = {"name": "find_ticket_categories", "args": args, "id": "call-1", "type": "tool_call"}
    state = asyncio.run(graph.ainvoke(
        {"messages": [*history, AIMessage(content="", tool_calls=[call])]},
        context=UserContext(uniticket=client),
    ))
    return json.loads(state["messages"][-1].content), client


def test_the_assistant_gets_the_tool_that_searches_and_decides_and_the_form_schema():
    assert [tool.name for tool in tools.tools] == ["find_ticket_categories", "get_form_schema"]


def test_the_model_sees_only_the_query_and_the_exclusions():
    parameters = convert_to_openai_tool(tools.find_ticket_categories)["function"]["parameters"]

    assert set(parameters["properties"]) == {"query", "excluded_category_ids"}
    assert parameters["required"] == ["query"]


def test_the_search_results_go_to_the_decision_model_in_their_order(find_graph, fake_decision_model):
    found = [make_category(2, "Certificato di laurea"), make_category(1, "Pagamento tasse")]

    decision, _ = run_find(find_graph, found)

    assert fake_decision_model.received == found
    assert decision == {"action": "PROPOSE", "categories": [
        {"id": 2, "name": "Certificato di laurea", "description": "", "structure_id": 1, "structure_name": ""},
    ]}


def test_the_excluded_categories_are_passed_to_the_search(find_graph):
    _, client = run_find(find_graph, [make_category(1)], excluded=[7])

    client.search_ticket_categories.assert_awaited_once_with("certificato di laurea", excluded_category_ids=[7])


def test_without_search_results_there_is_no_match(find_graph):
    decision, _ = run_find(find_graph, [])

    assert decision == {"action": "NO_MATCH", "categories": []}


def decided(action, *ids):
    """Un risultato passato di find_ticket_categories, come resta nella conversazione."""
    content = json.dumps({"action": action, "categories": [{"id": category_id} for category_id in ids]})
    return ToolMessage(content=content, name="find_ticket_categories", tool_call_id=f"call-{action}")


def test_the_conversation_recognizes_the_results_of_the_find_tool():
    assert tools.find_ticket_categories.name == conversation.FIND_TOOL


def test_a_reply_that_starts_with_yes_or_no():
    for reply in ("sì", "Sì, ma studio fisica", "si", "si, studio informatica", "ok!", "va bene grazie", "«Certo»"):
        assert conversation.is_yes(reply), reply
    for reply in ("si tratta di un altro", "certosa la sede?", "no", "non lo so", "", "vabbè"):
        assert not conversation.is_yes(reply), reply
    assert conversation.is_no("No, ho fatto chimica")
    assert not conversation.is_no("non lo so")
    assert not conversation.is_no("nope")


def test_questions_are_counted_for_the_current_request_only():
    assert conversation.questions_asked([decided("ASK", 1), decided("ASK", 2)]) == 2
    assert conversation.questions_asked([decided("ASK", 1), decided("CONFIRM", 2)]) == 1
    assert conversation.questions_asked([decided("ASK", 1), decided("PROPOSE", 2), decided("ASK", 3)]) == 1
    assert conversation.questions_asked([decided("ASK", 1), decided("NO_MATCH")]) == 0


def test_finding_stops_asking_when_no_match_stays_the_most_probable(find_graph, monkeypatch):
    class Unlikely(FirstCandidateModel):
        def estimate(self, query, candidates):
            return Estimate(categories=[(candidates[0], 0.3)], no_match=0.7)

    monkeypatch.setattr(tools, "decision_model", Unlikely())
    found = [make_category(1, "Pagamento tasse")]

    first, _ = run_find(find_graph, found)
    second, _ = run_find(find_graph, found, history=[decided("ASK", 1)])

    assert first["action"] == "ASK"
    assert second == {"action": "NO_MATCH", "categories": []}
