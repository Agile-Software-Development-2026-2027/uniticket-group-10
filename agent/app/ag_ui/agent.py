import logging
from typing import Any

from ag_ui.core import EventType, RunAgentInput, RunErrorEvent, StateSnapshotEvent
from ag_ui_langgraph import LangGraphAgent

from ..client.context import UserContext

ALLOWED_EVENTS = {
    EventType.RUN_STARTED,
    EventType.RUN_FINISHED,
    EventType.RUN_ERROR,
    EventType.TEXT_MESSAGE_START,
    EventType.TEXT_MESSAGE_CONTENT,
    EventType.TEXT_MESSAGE_END,
    EventType.TOOL_CALL_START,
    EventType.TOOL_CALL_END,
    EventType.TOOL_CALL_RESULT,
    EventType.STATE_SNAPSHOT,
}

logger = logging.getLogger(__name__)


def _parse_category_id(state: Any) -> int | None:
    if not isinstance(state, dict):
        return None
    raw = state.get("category_id")
    if raw in (None, "") or isinstance(raw, bool):
        return None
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


class SaferAgent(LangGraphAgent):
    def __init__(self, *, allow_events: set[EventType] | None = ALLOWED_EVENTS, **kwargs):
        super().__init__(**kwargs)
        self.allow_events = allow_events

    def clone(self):
        agent = super().clone()
        agent.allow_events = self.allow_events
        return agent

    async def run(self, input: RunAgentInput):
        async for event in super().run(input):
            if self.allow_events is not None and event.type not in self.allow_events:
                continue
            if event.type == EventType.RUN_ERROR:
                logger.error(event.message)
                yield RunErrorEvent(type=EventType.RUN_ERROR, message="An unexpected error occurred.")
            else:
                yield event


class UniTicketAgent(SaferAgent):
    _runtime_context: UserContext | None = None

    def for_request(self, context: UserContext) -> "UniTicketAgent":
        """Crea una nuova istanza dell'agente con il contesto runtime nuovo."""
        agent = self.clone()
        if agent is self:
            raise RuntimeError("Agent cloning returned the original instance")

        if context is self._runtime_context:
            raise ValueError("Runtime context must be a new instance")

        agent._runtime_context = context
        return agent

    def get_stream_kwargs(self, **kwargs):
        if self._runtime_context is None:
            raise RuntimeError("Contesto runtime mancante: crea l'agente con for_request().")

        options = super().get_stream_kwargs(**kwargs)
        options["context"] = self._runtime_context
        return options

    async def run(self, input: RunAgentInput):
        if self._runtime_context is not None and isinstance(input.state, dict):
            self._runtime_context.category_id = _parse_category_id(input.state)

            raw_fields = input.state.get("form_fields")
            if isinstance(raw_fields, dict):
                self._runtime_context.form_fields = dict(raw_fields)

        async for event in super().run(input):
            yield event

        if (
            self._runtime_context is not None
            and (
                self._runtime_context.category_id is not None
                or self._runtime_context.form_fields
            )
            and (self.allow_events is None or EventType.STATE_SNAPSHOT in self.allow_events)
        ):
            yield StateSnapshotEvent(
                type=EventType.STATE_SNAPSHOT,
                snapshot={
                    "category_id": self._runtime_context.category_id,
                    "form_fields": dict(self._runtime_context.form_fields),
                },
            )