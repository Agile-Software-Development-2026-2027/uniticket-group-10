import logging

from ag_ui_langgraph import LangGraphAgent
from ag_ui.core import EventType, RunAgentInput, RunErrorEvent

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
}

logger = logging.getLogger(__name__)


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


# Propone "configurable" per passare il contesto https://github.com/CopilotKit/CopilotKit/issues/3177#issuecomment-5360877173
# poi si rimangia la parola... e dice di aprire una nuova issue. In ogni caso la documentazione è fatta male.
# Configurable sembra servire per altre robe che non ho ancora capito, non è compito suo ricevere roba del RuntimeContext...
# Alla fine ho usato questo approccio: https://github.com/CopilotKit/CopilotKit/issues/2646#issuecomment-3965644665
class UniTicketAgent(SaferAgent):
    _runtime_context: UserContext = None

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
            raw_category = input.state.get("category_id")
            if raw_category in (None, ""):
                raw_category = input.state.get("selectedCategory")
            if raw_category not in (None, ""):
                try:
                    self._runtime_context.category_id = int(raw_category)
                except (TypeError, ValueError):
                    self._runtime_context.category_id = None
            else:
                self._runtime_context.category_id = None

            raw_fields = input.state.get("form_fields") or input.state.get("formFields")
            if isinstance(raw_fields, dict):
                self._runtime_context.form_fields = dict(raw_fields)

        async for event in super().run(input):
            yield event