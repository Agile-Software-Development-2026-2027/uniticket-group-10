"""La conferma del dipartimento: una categoria di dipartimento è certa solo se l'utente lo ha nominato."""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from app import tools
from app.client.api import UniTicketAPI
from app.client.context import UserContext
from app.decision import Decision, confirm_department, departments
from helpers import FirstCandidateModel, make_category

LAUREA_DIBEST = make_category(1, "Richiesta certificato di laurea", structure_name="DiBEST")
TASSE = make_category(2, "Pagamento tasse", structure_name="Servizi Didattici")


def test_departments_are_recognized_by_name_acronym_and_degree_course():
    assert departments.named_in("sono iscritta al DiBEST") == {"dibest"}
    assert departments.named_in("Dipartimento di Fisica, terzo anno") == {"fisica"}
    assert departments.named_in("faccio giurisprudenza") == {"discag"}
    assert departments.named_in("studio Ingegneria per l'Ambiente") == {"diam"}


def test_part_of_a_word_or_a_generic_word_names_no_department():
    assert departments.named_in("fisicamente non riesco a venire") == set()
    assert departments.named_in("mi serve un certificato di laurea in scienze") == set()


def test_a_department_category_is_confirmed_if_the_user_did_not_name_the_department():
    decision = confirm_department(Decision("PROPOSE", [LAUREA_DIBEST]), "mi serve un certificato di laurea")

    assert decision == Decision("CONFIRM", [LAUREA_DIBEST])


def test_it_is_proposed_if_the_user_named_the_department_or_one_of_its_courses():
    proposal = Decision("PROPOSE", [LAUREA_DIBEST])

    assert confirm_department(proposal, "sono del DiBEST e mi serve un certificato di laurea") == proposal
    assert confirm_department(proposal, "studio Biologia. Mi serve un certificato di laurea") == proposal


def test_the_confirmation_is_asked_only_once_and_only_for_a_single_department_category():
    alone = Decision("PROPOSE", [LAUREA_DIBEST])

    assert confirm_department(alone, "sì", asked={1}) == alone
    assert confirm_department(Decision("PROPOSE", [TASSE]), "devo pagare le tasse").action == "PROPOSE"
    assert confirm_department(Decision("PROPOSE", [LAUREA_DIBEST, TASSE]), "laurea").action == "PROPOSE"
    assert confirm_department(Decision("ASK", [LAUREA_DIBEST]), "laurea").action == "ASK"


@pytest.fixture(autouse=True)
def fake_decision_model(monkeypatch):
    monkeypatch.setattr(tools, "decision_model", FirstCandidateModel())


@pytest.fixture
def client():
    """Django finto: la ricerca restituisce il certificato del DiBEST, tranne quando è escluso."""
    fake = AsyncMock(spec=UniTicketAPI)

    async def search(query, excluded_category_ids=None, structure_ids=None):
        return [c for c in [LAUREA_DIBEST, TASSE] if c.id not in (excluded_category_ids or [])]

    fake.search_ticket_categories.side_effect = search
    return fake


def find(client, history):
    """Chiama find_ticket_categories dopo i messaggi dati, come farebbe il grafo."""
    workflow = StateGraph(MessagesState, context_schema=UserContext)
    workflow.add_node("tools", ToolNode([tools.find_ticket_categories]))
    workflow.add_edge(START, "tools")
    workflow.add_edge("tools", END)
    call = {"name": "find_ticket_categories", "args": {"query": "certificato di laurea"}, "id": "call-2",
            "type": "tool_call"}
    state = asyncio.run(workflow.compile().ainvoke(
        {"messages": [*history, AIMessage(content="", tool_calls=[call])]}, context=UserContext(uniticket=client)))
    return json.loads(state["messages"][-1].content)


def answered(decision):
    return ToolMessage(content=json.dumps(decision), name="find_ticket_categories", tool_call_id="call-1")


def test_the_tool_reads_the_department_in_the_words_of_the_user(client):
    unknown = find(client, [HumanMessage("Mi serve un certificato di laurea")])
    known = find(client, [HumanMessage("Mi serve un certificato"), HumanMessage("di laurea, studio Biologia")])

    assert unknown["action"] == "CONFIRM"
    assert unknown["department"] == "Dipartimento di Biologia, Ecologia e Scienze della Terra (DiBEST)"
    assert len(unknown["courses"]) == 3
    assert [category["id"] for category in unknown["categories"]] == [1]
    assert known["action"] == "PROPOSE"


def test_the_tool_does_not_ask_again_after_a_confirmation(client):
    first = find(client, [HumanMessage("Mi serve un certificato di laurea")])

    again = find(client, [HumanMessage("Mi serve un certificato di laurea"), answered(first), HumanMessage("sì")])

    assert again["action"] == "PROPOSE"


def test_the_tool_drops_the_category_if_the_user_is_of_another_department(client):
    first = find(client, [HumanMessage("Mi serve un certificato di laurea")])

    again = find(client, [HumanMessage("Mi serve un certificato di laurea"), answered(first),
                          HumanMessage("Studentessa di Giurisprudenza")])

    assert 1 not in [category["id"] for category in again["categories"]]
    assert client.search_ticket_categories.await_args.kwargs["excluded_category_ids"] == [1]


def test_a_department_named_before_the_confirmation_does_not_drop_the_category(client):
    first = find(client, [HumanMessage("Mi serve un certificato di laurea")])
    asked = answered(first)

    assert tools.confirmations_declined([HumanMessage("Ho un amico a Giurisprudenza"), asked, HumanMessage("sì")]) == []
    assert tools.confirmations_declined([asked, HumanMessage("studio Biologia, non Fisica")]) == []
    assert tools.confirmations_declined([asked, HumanMessage("faccio giurisprudenza")]) == [1]
