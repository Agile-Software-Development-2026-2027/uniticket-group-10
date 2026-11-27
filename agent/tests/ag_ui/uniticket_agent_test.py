import unittest
from unittest.mock import Mock, patch

from ag_ui.core import EventType, RunAgentInput, RunFinishedEvent, RunStartedEvent
from ag_ui_langgraph import LangGraphAgent
from langgraph.graph import END, START, StateGraph

from app.ag_ui.agent import UniTicketAgent
from app.client.api import UniTicketAPI
from app.client.context import UserContext, ConversationContext


def make_graph():
    builder = StateGraph(dict)
    builder.add_node("respond", lambda state: {})
    builder.add_edge(START, "respond")
    builder.add_edge("respond", END)
    return builder.compile()


class UniTicketAgentTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.agent = UniTicketAgent(name="uniticket", graph=make_graph())
        self.context = UserContext(
                uniticket=Mock(spec=UniTicketAPI),
                user=UserContext(
                    first_name="Ciccio",
                    last_name="Pasticcio",
                    email="ciccio.pasticcio@unical.it",
                    identifier=676767,
                    is_employee=True,
                )
            )
        self.agent._runtime_context = self.context

    def test_clone_does_not_copy_runtime_context(self):
        cloned = self.agent.clone()

        self.assertIsNone(cloned._runtime_context)
        self.assertIs(self.agent._runtime_context, self.context)

    def test_for_request_uses_new_context_without_changing_original(self):
        context = UserContext(
                uniticket=Mock(spec=UniTicketAPI),
                user=UserContext(
                    first_name="Ciccio",
                    last_name="Pasticcio",
                    email="ciccio.pasticcio@unical.it",
                    identifier=676767,
                    is_employee=True,
                )
            )

        request_agent = self.agent.for_request(context)

        self.assertIs(request_agent._runtime_context, context)
        self.assertIs(self.agent._runtime_context, self.context)
        self.assertIsNot(request_agent._runtime_context, self.agent._runtime_context)

    async def test_clone_preserves_allowed_events_and_filters_stream(self):
        self.agent.allow_events = {EventType.RUN_FINISHED}
        cloned = self.agent.clone()
        self.assertEqual(cloned.allow_events, {EventType.RUN_FINISHED})

        input_data = RunAgentInput(
            thread_id="thread-1", run_id="run-1", messages=[],
            state={}, tools=[], context=[], forwarded_props={},
        )
        started = RunStartedEvent(type=EventType.RUN_STARTED, thread_id="thread-1", run_id="run-1")
        finished = RunFinishedEvent(type=EventType.RUN_FINISHED, thread_id="thread-1", run_id="run-1")

        async def events(agent, input):
            yield started
            yield finished

        with patch.object(LangGraphAgent, "run", events):
            received = [event async for event in cloned.run(input_data)]

        self.assertEqual(received, [finished])
