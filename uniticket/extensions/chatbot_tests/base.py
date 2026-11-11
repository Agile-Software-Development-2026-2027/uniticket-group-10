from unittest.mock import patch

import httpx
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from assistant.models import AssistantThread


@override_settings(ROOT_URLCONF="assistant.urls", ASSISTANT_AGENT_URL="http://agent:8001/conversation")
class ProxyTestCase(TestCase):
    """Run the real proxy; MockTransport records requests and returns self.upstream."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="session-user")
        self.thread = AssistantThread.objects.create(user=self.user)
        self.payload = {"threadId": str(self.thread.id)}
        self.client = APIClient()
        self.client.force_login(self.user)
        self.client.credentials(HTTP_ACCEPT="text/event-stream")
        self.requests = []
        self.upstream = httpx.Response(
            200, headers={"Content-Type": "text/event-stream"}, stream=httpx.ByteStream(b""),
        )
        client_class = httpx.Client

        def create_client(**kwargs):
            self.http_client = client_class(
                transport=httpx.MockTransport(self.handle_request), **kwargs,
            )
            self.addCleanup(self.http_client.close)
            return self.http_client

        patcher = patch("assistant.api.httpx.Client", side_effect=create_client)
        patcher.start()
        self.addCleanup(patcher.stop)

    def handle_request(self, request):
        self.requests.append(request)
        return self.upstream

    def post(self, **headers):
        response = self.client.post("/api/assistant", self.payload, format="json", **headers)
        self.addCleanup(response.close)
        return response
