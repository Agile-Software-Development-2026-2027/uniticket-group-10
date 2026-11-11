from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from assistant.models import AssistantThread


@override_settings(ROOT_URLCONF="assistant.urls")
class ThreadPermissionsTests(TestCase):
    def setUp(self):
        self.person_a = get_user_model().objects.create_user(username="person_a")
        self.person_b = get_user_model().objects.create_user(username="person_b")
        self.person_a_client = APIClient()
        self.person_a_client.force_login(self.person_a)
        self.thread = AssistantThread.objects.create(user=self.person_a)

    def test_authenticated_user_creates_owned_thread(self):
        response = self.person_a_client.post("/api/assistant/thread/new/")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(AssistantThread.objects.get(pk=response.data["thread_id"]).user, self.person_a)

    @patch("assistant.api.httpx.Client")
    def test_other_users_thread_is_rejected_before_agent(self, http_client_mock):
        thread = AssistantThread.objects.create(user=self.person_b)

        response = self.person_a_client.post(
            "/api/assistant", {"threadId": str(thread.id)}, format="json",
        )

        self.assertEqual(response.status_code, 403)
        http_client_mock.assert_not_called()

    @patch("assistant.api.httpx.Client")
    def test_missing_thread_id_is_rejected(self, http_client_mock):
        response = self.person_a_client.post("/api/assistant", {}, format="json")

        self.assertEqual(response.status_code, 400)
        http_client_mock.assert_not_called()

    @patch("assistant.api.httpx.Client")
    def test_invalid_thread_id_is_rejected(self, http_client_mock):
        response = self.person_a_client.post(
            "/api/assistant", {"threadId": "invalid"}, format="json",
        )

        self.assertEqual(response.status_code, 400)
        http_client_mock.assert_not_called()

    @patch("assistant.api.httpx.Client")
    def test_unknown_thread_is_rejected(self, http_client_mock):
        response = self.person_a_client.post(
            "/api/assistant", {"threadId": str(uuid4())}, format="json",
        )

        self.assertEqual(response.status_code, 403)
        http_client_mock.assert_not_called()

    @patch("assistant.api.httpx.Client")
    def test_anonymous_cannot_create_or_access_threads(self, upstream):
        self.person_a_client.logout()
        for path, data in (("/api/assistant/thread/new/", {}),
                           ("/api/assistant", {"threadId": str(self.thread.id)})):
            self.assertEqual(self.person_a_client.post(path, data, format="json").status_code, 403)
        self.assertEqual(AssistantThread.objects.count(), 1)
        upstream.assert_not_called()
