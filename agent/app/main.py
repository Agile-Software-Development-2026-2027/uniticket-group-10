import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .conversation import ConversationError
from .graph import graph
from .contracts import AgentRequest


logger = logging.getLogger(__name__)


app = FastAPI(title="UniTicket assistant", docs_url=None, redoc_url=None)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/conversation")
def converse(request: AgentRequest):
    try:
        return {"messages": graph.invoke({"request": request})["messages"]}
    except ConversationError as error:
        return JSONResponse(error.detail, status_code=error.status)
    except Exception:
        logger.exception("Agent execution failed")
        return JSONResponse({"detail": "Agent execution failed"}, status_code=503)
