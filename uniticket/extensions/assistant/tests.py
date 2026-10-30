import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from .api import search


class SearchTests(SimpleTestCase):
    def post(self, body, *, authenticated=True, content_type="application/json"):
        request = APIRequestFactory().post("/api/search", body, content_type=content_type)
        if authenticated:
            force_authenticate(request, user=SimpleNamespace(is_authenticated=True))
        return search(request)

    def test_requires_login(self):
        self.assertEqual(self.post(b'{}', authenticated=False).status_code, 403)

    def test_requires_json(self):
        self.assertEqual(self.post(b'{}', content_type="text/plain").status_code, 415)

    def test_rejects_invalid_payloads(self):
        payloads = [b'{', b'\xff', b'[]', b'{}']
        payloads += [json.dumps({"query": value}).encode() for value in (
            None, 123, 1.5, True, [], {}, "", "   ", "x" * 501,
        )]
        with patch("assistant.api.retrieval_service.search") as retrieve:
            for body in payloads:
                with self.subTest(body=body):
                    response = self.post(body)
                    self.assertEqual(response.status_code, 400)
                    self.assertTrue(response.data)
            retrieve.assert_not_called()

    def test_searches_with_trimmed_query(self):
        tickets = [{"ticket_id": 316}]
        with patch("assistant.api.retrieval_service.search", return_value=tickets) as retrieve:
            response = self.post(b'{"query": "  certificato  "}')
        retrieve.assert_called_once_with("certificato")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"tickets": tickets})

    def test_accepts_maximum_length(self):
        with patch("assistant.api.retrieval_service.search", return_value=[]):
            response = self.post(json.dumps({"query": "x" * 500}).encode())
        self.assertEqual(response.status_code, 200)

    def test_requires_post(self):
        request = APIRequestFactory().get("/api/search")
        force_authenticate(request, user=SimpleNamespace(is_authenticated=True))
        self.assertEqual(search(request).status_code, 405)

    def test_accepts_json_with_charset(self):
        with patch("assistant.api.retrieval_service.search", return_value=[]):
            response = self.post(b'{"query": "certificato"}',
                                 content_type="application/json; charset=utf-8")
        self.assertEqual(response.status_code, 200)

    def test_enforces_session_csrf(self):
        # CSRF (Cross-Site Request Forgery): un sito malevolo può indurre il browser
        # a inviare richieste usando i cookie di sessione di un utente autenticato.
        # Django richiede un token CSRF valido per le richieste POST autenticate
        # tramite sessione. Questo test verifica il rifiuto senza token (403)
        # e l'accettazione con cookie e header X-CSRFToken corrispondenti (200),
        # senza usare force_authenticate, che bypasserebbe il controllo di sessione.
        factory = APIRequestFactory(enforce_csrf_checks=True)
        user = SimpleNamespace(is_authenticated=True, is_active=True)
        with patch("assistant.api.retrieval_service.search", return_value=[]) as retrieve:
            request = factory.post("/api/search", {"query": "certificato"}, format="json")
            request.user = user
            self.assertEqual(search(request).status_code, 403)
            retrieve.assert_not_called()

            token = "a" * 32
            request = factory.post("/api/search", {"query": "certificato"},
                                   format="json", HTTP_X_CSRFTOKEN=token)
            request.COOKIES["csrftoken"] = token
            request.user = user
            self.assertEqual(search(request).status_code, 200)
            retrieve.assert_called_once_with("certificato")
