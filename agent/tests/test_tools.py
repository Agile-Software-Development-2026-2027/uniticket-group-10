import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from app import tools
from app.client.api import FormField, FormFieldUpdateResult, FormSchema, UniTicketAPI
from app.client.context import UserContext
from helpers import FirstCandidateModel, make_category


@pytest.fixture(autouse=True)
def fake_decision_model(monkeypatch):
    """Sostituisce Jev con un modello finto: i test non hanno bisogno del server."""
    model = FirstCandidateModel()
    monkeypatch.setattr(tools, "decision_model", model)
    return model


@pytest.fixture
def decision_graph():
    workflow = StateGraph(MessagesState, context_schema=UserContext)
    workflow.add_node("tools", ToolNode([tools.decide_ticket_categories]))
    workflow.add_edge(START, "tools")
    workflow.add_edge("tools", END)
    return workflow.compile()


@pytest.fixture
def set_field_graph():
    workflow = StateGraph(MessagesState, context_schema=UserContext)
    workflow.add_node("tools", ToolNode([tools.set_field]))
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
        context=UserContext(uniticket=client),
    ))
    return json.loads(state["messages"][-1].content)


def run_set_field(graph, client, field_id, value, category_id=10, form_fields=None):
    call = {
        "name": "set_field",
        "args": {"field_id": field_id, "value": value},
        "id": "call-set-field",
        "type": "tool_call",
    }
    state = asyncio.run(graph.ainvoke(
        {"messages": [AIMessage(content="", tool_calls=[call])]},
        context=UserContext(
            uniticket=client,
            category_id=category_id,
            form_fields=form_fields if form_fields is not None else {},
        ),
    ))
    return json.loads(state["messages"][-1].content)


def make_email_field(disabled: bool = False) -> FormField:
    return FormField(
        id="email",
        label="Email",
        type="email",
        required=True,
        constraints={},
        initial_value=None,
        disabled=disabled,
    )


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


def test_set_field_updates_valid_field_in_opened_form(set_field_graph):
    client = AsyncMock(spec=UniTicketAPI)
    client.get_form_schema.return_value = FormSchema(
        category_id=10,
        module_id=1,
        fields=[make_email_field()],
    )
    client.update_form_field.return_value = FormFieldUpdateResult(
        valid=True,
        field_id="email",
        value="mario@unical.it",
    )

    result = run_set_field(set_field_graph, client, "email", "mario@unical.it", category_id=10)

    assert result == {
        "ok": True,
        "category_id": 10,
        "field_id": "email",
        "value": "mario@unical.it",
    }
    client.update_form_field.assert_awaited_once_with(
        category_id=10,
        field_id="email",
        value="mario@unical.it",
        data=None,
    )


def test_set_field_rejects_field_not_in_opened_form(set_field_graph):
    client = AsyncMock(spec=UniTicketAPI)
    client.get_form_schema.return_value = FormSchema(
        category_id=10,
        module_id=1,
        fields=[make_email_field()],
    )

    result = run_set_field(set_field_graph, client, "campo_inesistente", "valore", category_id=10)

    assert result["ok"] is False
    assert "campo_inesistente" in result["error"]
    client.update_form_field.assert_not_called()


def test_set_field_returns_error_when_no_form_is_open(set_field_graph):
    client = AsyncMock(spec=UniTicketAPI)

    result = run_set_field(set_field_graph, client, "email", "mario@unical.it", category_id=None)

    assert result["ok"] is False
    assert "Nessun form" in result["error"]
    client.get_form_schema.assert_not_called()


def test_set_field_returns_validation_errors(set_field_graph):
    client = AsyncMock(spec=UniTicketAPI)
    client.get_form_schema.return_value = FormSchema(
        category_id=10,
        module_id=1,
        fields=[make_email_field()],
    )
    client.update_form_field.return_value = FormFieldUpdateResult(
        valid=False,
        field_id="email",
        errors=[{"field": "email", "code": "invalid", "message": "Inserisci un indirizzo email valido."}],
    )

    result = run_set_field(set_field_graph, client, "email", "non-valida", category_id=10)

    assert result["ok"] is False
    assert result["errors"][0]["code"] == "invalid"