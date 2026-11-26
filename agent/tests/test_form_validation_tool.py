"""Test unitari per il tool `validate_form` esposto all'agente."""

import asyncio
import json
from unittest.mock import AsyncMock

import httpx
from langchain_core.messages import AIMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from app import tools
from app.client.api import FieldValidationError, FormValidationResult, UniTicketAPI
from app.client.context import UserContext


def run_tool(client, ticket_id=42, data=None):
    workflow = StateGraph(MessagesState, context_schema=UserContext)
    workflow.add_node("tools", ToolNode([tools.validate_form]))
    workflow.add_edge(START, "tools")
    workflow.add_edge("tools", END)
    call = {
        "name": "validate_form",
        "args": {"ticket_id": ticket_id, "data": {} if data is None else data},
        "id": "validate-1",
        "type": "tool_call",
    }
    result = asyncio.run(
        workflow.compile().ainvoke(
            {"messages": [AIMessage(content="", tool_calls=[call])]},
            context=UserContext(uniticket=client),
        )
    )
    return result["messages"][-1]


def test_tool_is_registered_and_exposes_expected_parameters():
    assert tools.validate_form in tools.tools
    parameters = convert_to_openai_tool(tools.validate_form)["function"]["parameters"]
    assert set(parameters["properties"]) == {"ticket_id", "data"}
    assert set(parameters["required"]) == {"ticket_id", "data"}


def test_tool_returns_structured_validation_result():
    client = AsyncMock(spec=UniTicketAPI)
    expected = FormValidationResult(
        valid=False,
        missing_fields=["nome"],
        errors=[FieldValidationError(field="email", code="invalid", message="Email non valida.")],
    )
    client.validate_form.return_value = expected

    message = run_tool(client, ticket_id=42, data={"email": "non-valida"})

    assert json.loads(message.content) == expected.model_dump()
    client.validate_form.assert_awaited_once_with(42, {"email": "non-valida"})


def test_tool_rejects_invalid_ticket_ids():
    for invalid_id in [0, -1, "42", True]:
        client = AsyncMock(spec=UniTicketAPI)
        message = run_tool(client, ticket_id=invalid_id, data={})
        assert message.status == "error"
        client.validate_form.assert_not_called()


def test_tool_reports_api_errors_without_leaking_details():
    client = AsyncMock(spec=UniTicketAPI)
    for status in [401, 403, 404, 409, 500]:
        response = httpx.Response(status, request=httpx.Request("POST", "http://uniticket.test/"))
        client.validate_form.side_effect = httpx.HTTPStatusError(
            "Errore interno", request=response.request, response=response
        )
        result = json.loads(run_tool(client).content)
        assert result["status"] == status
        assert "error" in result and "valid" not in result

    for error, status in [
        (httpx.ConnectError("Dettaglio privato"), 503),
        (ValueError("Risposta errata"), 502),
    ]:
        client.validate_form.side_effect = error
        result = json.loads(run_tool(client).content)
        assert result["status"] == status
        assert str(error) not in result["error"]
