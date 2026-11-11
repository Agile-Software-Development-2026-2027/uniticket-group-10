"""Authenticated AG-UI proxy to the internal agent service."""

import logging

import httpx

from django.conf import settings
from django.http import StreamingHttpResponse
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AssistantThread

logger = logging.getLogger(__name__)


class AgentRequestSerializer(serializers.Serializer):
    threadId = serializers.UUIDField()


class AgentStream:
    """Stream upstream events and release HTTP resources on close."""

    def __init__(self, client: httpx.Client, upstream: httpx.Response):
        self.client = client
        self.upstream = upstream
        self.closed = False

    def __iter__(self):
        try:
            yield from self.upstream.iter_bytes()
        finally:
            self.close()

    def close(self):
        if self.closed:
            return

        self.closed = True
        try:
            self.upstream.close()
        finally:
            self.client.close()


class AgentProxyView(APIView):
    """Forward authenticated AG-UI requests to the internal agent."""

    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    def perform_content_negotiation(self, request, force=False):
        # Allow SSE requests while keeping DRF errors in JSON.
        return JSONRenderer(), "application/json"

    def post(self, request):
        serializer = AgentRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        thread_id = serializer.validated_data["threadId"]

        if not AssistantThread.objects.filter(id=thread_id, user=request.user).exists():
            raise PermissionDenied("Thread not found or access denied")

        client = httpx.Client(
            timeout=httpx.Timeout(150.0, connect=10.0),
            follow_redirects=False,
        )

        try:
            upstream_request = client.build_request(
                "POST",
                settings.ASSISTANT_AGENT_URL,
                json=request.data,
                headers={"Accept": "text/event-stream"},
            )
            upstream = client.send(upstream_request, stream=True)
        except httpx.RequestError:
            client.close()
            logger.exception("Agent request failed (thread_id=%s)", thread_id)
            return Response({"detail": "Agent unavailable"}, status=503)

        stream = AgentStream(client, upstream)
        content_type = upstream.headers.get("content-type", "").split(";", 1)[0].strip().lower()

        if upstream.status_code != 200 or content_type != "text/event-stream":
            stream.close()
            logger.error(
                "Agent response rejected (thread_id=%s, status=%s, content_type=%s)",
                thread_id, upstream.status_code, content_type,
            )
            return Response({"detail": "Invalid agent response"}, status=502)

        response = StreamingHttpResponse(stream, content_type="text/event-stream")
        response["Cache-Control"] = "no-store"
        return response
