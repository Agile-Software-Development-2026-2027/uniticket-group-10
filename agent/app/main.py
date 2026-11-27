
"""FastAPI AG-UI backend for UniTicket."""

import logging
from ag_ui.core import RunAgentInput
from ag_ui.encoder import EventEncoder
from fastapi import Depends, FastAPI, HTTPException, Header, Request
from fastapi.responses import StreamingResponse
from langgraph.checkpoint.memory import InMemorySaver

from .client.client import UniTicketClient
from .client.context import UserContext

from .graph import create_graph
from .ag_ui.agent import UniTicketAgent

logger = logging.getLogger(__name__)
app = FastAPI(title="UniTicket assistant")

agent = UniTicketAgent(
    name="uniticket",
    graph=create_graph(checkpointer=InMemorySaver()),
    emit_raw_events=False,
    config={"recursion_limit": 12}, # <-- Quante iterazioni può fare l'agente per uno step, serve per evitare loop strani
)

# Un giorno farà dei controlli seri... forse
def require_session_cookie(cookie: str = Header(alias="Cookie")) -> str:
    if not cookie or not cookie.strip():
        raise HTTPException(status_code=401, detail="Session cookie required")
    return cookie

@app.post("/conversation")
async def run_agent(input_data: RunAgentInput, request: Request, session_cookie: str = Depends(require_session_cookie)):
    # Based on the official ag_ui_langgraph endpoint implementation:
    # https://github.com/ag-ui-protocol/ag-ui/blob/main/integrations/langgraph/python/ag_ui_langgraph/endpoint.py
    # Praticamente fanno una roba strana, prendono l'istanza di base, e per ogni richiesta clonano l'agente...? 
    # Faccio la stessa cosa (copia e incolla e inietto il Context quando faccio la clonazione)

    accept_header = request.headers.get("accept")
    encoder = EventEncoder(accept=accept_header)

    request_data = await request.json()

    async def event_generator():
        async with UniTicketClient(session_cookie=session_cookie) as client:
            if "selected_form" in request_data:
                selected_form = request_data["selected_form"]
                # Do something with this...

            # Create context.
            ctx = UserContext(
                uniticket=client,
                user_first_name=request_data["user_first_name"],
                user_last_name=request_data["user_last_name"],
                user_email=request_data["user_email"],
                user_identifier=request_data["user_identifier"],
                user_is_employee=request_data["user_is_employee"],
                )

            request_agent = agent.for_request(ctx) # Clona agent e le assegna il context
            async for event in request_agent.run(input_data):
                yield encoder.encode(event)

    return StreamingResponse(event_generator(), media_type=encoder.get_content_type())

@app.get("/health")
def health():
    return {"status": "ok"}
