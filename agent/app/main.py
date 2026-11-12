
"""FastAPI AG-UI backend for UniTicket."""

import logging

from ag_ui.core import EventType, RunAgentInput, RunErrorEvent
from ag_ui.encoder import EventEncoder
from ag_ui_langgraph import LangGraphAgent
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from langgraph.checkpoint.memory import InMemorySaver

from .graph import workflow

logger = logging.getLogger(__name__)
app = FastAPI(title="UniTicket assistant")

graph = workflow.compile(checkpointer=InMemorySaver())
agent = LangGraphAgent(
    name="uniticket",
    graph=graph,
    emit_raw_events=False,
    config={"recursion_limit": 12}, # <-- Quante iterazioni può fare l'agente per uno step, serve per evitare loop strani
)

#
# We need to inspect the actual payload of each AG-UI event emitted
# to identify whether it could expose sensitive information to the frontend.
#
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
    #EventType.TOOL_CALL_ARGS,
}

@app.post("/conversation")
async def run_agent(input_data: RunAgentInput, request: Request):
    # Based on the official ag_ui_langgraph endpoint implementation:
    # https://github.com/ag-ui-protocol/ag-ui/blob/main/integrations/langgraph/python/ag_ui_langgraph/endpoint.py
    # Adds event filtering and sanitizes RUN_ERROR messages to prevent leaking internal details.
    accept_header = request.headers.get("accept")
    encoder = EventEncoder(accept=accept_header)
    request_agent = agent.clone()

    async def event_generator():
        async for event in request_agent.run(input_data):
            if event.type not in ALLOWED_EVENTS:
                continue

            if event.type == EventType.RUN_ERROR:
                logger.error("Agent returned RUN_ERROR (run_id=%s)", input_data.run_id)
                event = RunErrorEvent(type=EventType.RUN_ERROR, message="Run error")
            yield encoder.encode(event)

    return StreamingResponse(
        event_generator(),
        media_type=encoder.get_content_type()
    )


@app.get("/health")
def health():
    return {"status": "ok"}
