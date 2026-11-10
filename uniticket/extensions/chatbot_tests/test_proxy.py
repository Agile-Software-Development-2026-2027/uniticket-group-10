import json
from unittest.mock import patch
from uuid import uuid4

import httpx
from django.conf import settings

from .base import ProxyTestCase


class AgUiProxyTests(ProxyTestCase):
    def test_forwards_payload_to_agent(self):
        self.payload.update({
            "runId": str(uuid4()),
            "messages": [{"id": "u1", "role": "user", "content": "Ciao"}],
            "tools": [],
            "context": [],
            "state": {},
            "forwardedProps": {},
        })

        response = self.post()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.requests), 1)
        request = self.requests[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(str(request.url), settings.ASSISTANT_AGENT_URL)
        self.assertEqual(json.loads(request.content), self.payload)
        self.assertEqual(request.headers["Accept"], "text/event-stream")

    def test_network_failure_returns_json_even_when_accepting_sse(self):
        with patch.object(self, "handle_request", side_effect=httpx.ConnectError("offline")):
            response = self.post()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(response.json(), {"detail": "Agent unavailable"})
        self.assertTrue(self.http_client.is_closed)

    def test_redirect_is_rejected_without_following_it(self):
        self.upstream = httpx.Response(
            302,
            headers={"Location": "http://other-agent/"},
            stream=httpx.ByteStream(b""),
        )

        response = self.post()

        self.assertEqual(response.status_code, 502)
        self.assertEqual(len(self.requests), 1)
        self.assertTrue(self.upstream.is_closed)
        self.assertTrue(self.http_client.is_closed)

    def test_unexpected_content_type_is_rejected(self):
        self.upstream = httpx.Response(
            200,
            headers={"Content-Type": "text/html"},
            stream=httpx.ByteStream(b"<html/>"),
        )

        response = self.post()

        self.assertEqual(response.status_code, 502)
        self.assertTrue(self.upstream.is_closed)
        self.assertTrue(self.http_client.is_closed)

    def test_non_sse_responses_do_not_expose_agent_status_or_body(self):
        for status, body in (
            (200, b'{"detail": "internal secret"}'),
            (422, b'{"detail": "internal secret"}'),
            (500, b'internal traceback, not valid JSON'),
        ):
            with self.subTest(status=status):
                self.upstream = httpx.Response(
                    status,
                    headers={"Content-Type": "application/json"},
                    stream=httpx.ByteStream(body),
                )

                response = self.post()

                self.assertEqual(response.status_code, 502)
                self.assertEqual(response["Content-Type"], "application/json")
                self.assertEqual(response.json(), {"detail": "Invalid agent response"})
                self.assertTrue(self.upstream.is_closed)
                self.assertTrue(self.http_client.is_closed)
