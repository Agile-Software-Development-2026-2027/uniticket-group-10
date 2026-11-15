import unittest
from unittest.mock import patch

from ag_ui.core import (
    EventType,
    RawEvent,
    RunAgentInput,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from ag_ui_langgraph import LangGraphAgent
from langgraph.graph import END, START, StateGraph

from app.ag_ui.agent import SaferAgent


def make_graph():
    builder = StateGraph(dict)
    builder.add_node("respond", lambda state: {})
    builder.add_edge(START, "respond")
    builder.add_edge("respond", END)
    return builder.compile()


class SaferAgentTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.agent = SaferAgent(name="uniticket", graph=make_graph())
        self.input = RunAgentInput(
            thread_id="thread-1", run_id="run-1", messages=[],
            state={}, tools=[], context=[], forwarded_props={},
        )

    async def test_only_allowed_events_are_forwarded(self):
        allowed_events = [
            RunStartedEvent(type=EventType.RUN_STARTED, thread_id="thread-1", run_id="run-1"),
            TextMessageStartEvent(type=EventType.TEXT_MESSAGE_START, message_id="message-1", role="assistant"),
            TextMessageContentEvent(type=EventType.TEXT_MESSAGE_CONTENT, message_id="message-1", delta="Ciao"),
            TextMessageEndEvent(type=EventType.TEXT_MESSAGE_END, message_id="message-1"),
            ToolCallStartEvent(type=EventType.TOOL_CALL_START, tool_call_id="tool-1", tool_call_name="get_structures"),
            ToolCallEndEvent(type=EventType.TOOL_CALL_END, tool_call_id="tool-1"),
            ToolCallResultEvent(type=EventType.TOOL_CALL_RESULT, message_id="result-1", tool_call_id="tool-1", content="[]"),
            RunFinishedEvent(type=EventType.RUN_FINISHED, thread_id="thread-1", run_id="run-1"),
        ]

        async def events(agent, input):
            for event in allowed_events:
                yield RawEvent(type=EventType.RAW, event={"secret": "private-data"})
                yield event

        with patch.object(LangGraphAgent, "run", events):
            received = [event async for event in self.agent.run(self.input)]

        self.assertEqual(received, allowed_events)
        for actual, expected in zip(received, allowed_events):
            self.assertIs(actual, expected)

    async def test_clone_preserves_allowed_events_and_filters_stream(self):
        self.agent.allow_events = {EventType.RUN_FINISHED}
        cloned = self.agent.clone()
        self.assertEqual(cloned.allow_events, {EventType.RUN_FINISHED})

        started = RunStartedEvent(type=EventType.RUN_STARTED, thread_id="thread-1", run_id="run-1")
        finished = RunFinishedEvent(type=EventType.RUN_FINISHED, thread_id="thread-1", run_id="run-1")

        async def events(agent, input):
            yield started
            yield finished

        with patch.object(LangGraphAgent, "run", events):
            received = [event async for event in cloned.run(self.input)]

        self.assertEqual(received, [finished])

    async def test_run_error_does_not_leak_internal_details(self):
        secret = "Internal failure: api_key=private-test-key"
        internal_error = RunErrorEvent(
            type=EventType.RUN_ERROR, message=secret, code="PRIVATE_ERROR_CODE",
        )
        finished = RunFinishedEvent(type=EventType.RUN_FINISHED, thread_id="thread-1", run_id="run-1")

        async def events(agent, input):
            yield internal_error
            yield finished

        with patch.object(LangGraphAgent, "run", events), self.assertLogs(
            "app.ag_ui.agent", level="ERROR",
        ) as logs:
            received = [event async for event in self.agent.run(self.input)]

        self.assertEqual(received, [
            RunErrorEvent(type=EventType.RUN_ERROR, message="An unexpected error occurred."),
            finished,
        ])
        serialized = "".join(event.model_dump_json() for event in received)
        self.assertNotIn("private-test-key", serialized)
        self.assertNotIn("PRIVATE_ERROR_CODE", serialized)
        self.assertEqual(internal_error.message, secret)
        self.assertIn(secret, logs.output[0])
