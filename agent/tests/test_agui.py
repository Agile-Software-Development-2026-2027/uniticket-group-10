import json
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
from ag_ui.core import EventType, RawEvent, RunFinishedEvent, RunStartedEvent

from app.main import agent, app


class AgUiTests(unittest.IsolatedAsyncioTestCase):
    async def test_endpoint_does_not_forward_raw_events(self):
        payload = {
            "threadId": str(uuid4()),
            "runId": str(uuid4()),
            "messages": [{"id": "u1", "role": "user", "content": "Ciao"}],
            "state": {}, "tools": [], "context": [], "forwardedProps": {},
        }

        async def agent_events():
            yield RunStartedEvent(
                type=EventType.RUN_STARTED, thread_id=payload["threadId"], run_id=payload["runId"],
            )
            yield RawEvent(type=EventType.RAW, event={"system_prompt": "private-system-prompt"})
            yield RunFinishedEvent(
                type=EventType.RUN_FINISHED, thread_id=payload["threadId"], run_id=payload["runId"],
            )

        with patch.object(agent, "clone") as clone:
            clone.return_value.run.return_value = agent_events()
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://agent",
            ) as client:
                response = await client.post(
                    "/conversation", json=payload,
                    headers={"Accept": "text/event-stream"},
                )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
        events = [
            json.loads(line.removeprefix("data: "))
            for line in response.text.splitlines() if line.startswith("data: ")
        ]
        event_types = [event["type"] for event in events]
        self.assertEqual(event_types, ["RUN_STARTED", "RUN_FINISHED"])
        self.assertNotIn("private-system-prompt", response.text)

    async def test_internal_exceptions_are_not_exposed_in_sse(self):
        secret = "Internal failure: api_key=private-test-key"
        payload = {
            "threadId": str(uuid4()),
            "runId": str(uuid4()),
            "messages": [{"id": "u1", "role": "user", "content": "Ciao"}],
            "state": {}, "tools": [], "context": [], "forwardedProps": {},
        }

        with patch("app.graph.llm", ainvoke=AsyncMock(side_effect=RuntimeError(secret))):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://agent",
            ) as client:
                response = await client.post(
                    "/conversation", json=payload,
                    headers={"Accept": "text/event-stream"},
                )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
        self.assertNotIn("private-test-key", response.text)
        events = [
            json.loads(line.removeprefix("data: "))
            for line in response.text.splitlines() if line.startswith("data: ")
        ]
        errors = [event for event in events if event["type"] == "RUN_ERROR"]
        self.assertEqual(errors, [{"type": "RUN_ERROR", "message": "Run error"}])
