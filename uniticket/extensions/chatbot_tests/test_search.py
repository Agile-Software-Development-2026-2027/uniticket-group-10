"""Test dell'endpoint di ricerca delle categorie tramite embeddings."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from organizational_area.models import OrganizationalStructure
from rest_framework.test import APIClient
from uni_ticket.models import TicketCategory

from assistant.catalog import available_categories

URL = "/api/assistant/search/"


@override_settings(ROOT_URLCONF="assistant.urls")
class CategorySearchTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="search-user")
        self.client = APIClient()
        self.client.force_login(self.user)

        # Due strutture e tre categorie vere nel database di test
        self.ict = OrganizationalStructure.objects.create(name="ICT", slug="ict", unique_code="ICT")
        dimes = OrganizationalStructure.objects.create(name="DIMES", slug="dimes", unique_code="DIMES")
        self.reset_2fa = TicketCategory.objects.create(
            name="Reset 2FA", slug="reset-2fa", description="Doppia autenticazione", organizational_structure=self.ict)
        self.reset_password = TicketCategory.objects.create(
            name="Reset password", slug="reset-password", description="Password", organizational_structure=self.ict)
        self.thesis = TicketCategory.objects.create(
            name="Tesi di laurea", slug="tesi", description="Tesi", organizational_structure=dimes)

        # Finti: categorie dell'utente, embedder (Ollama) e Qdrant
        self.available = patch("assistant.search.available_categories").start()
        self.available.return_value = [self.reset_2fa, self.reset_password, self.thesis]
        self.provider = patch("assistant.search.provider").start()
        self.provider.embed_query.return_value = [0.1, 0.2, 0.3]
        self.repository = patch("assistant.search.index_repository").start()
        self.addCleanup(patch.stopall)

    def searched_ids(self):
        """Gli id passati a Qdrant come categorie in cui cercare."""
        vector, top_k, ids = self.repository.search.call_args.args
        return set(ids)


    # verifica se le categorie tornano nell'ordine deciso da Qdrant
    def test_returns_categories_in_qdrant_order(self):
        self.repository.search.return_value = [self.thesis.id, self.reset_2fa.id]

        response = self.client.get(URL, {"query": "reset 2fa"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual([category["id"] for category in response.data], [self.thesis.id, self.reset_2fa.id])
        self.provider.embed_query.assert_called_once_with("reset 2fa")
        self.assertEqual(self.repository.search.call_args.args[1], 50)


    # verifica se i filtri excluded_category_ids e structure_ids funzionano
    def test_excluded_and_structure_filters_reach_qdrant(self):
        self.repository.search.return_value = []
        self.available.side_effect = available_categories

        with (
            patch("assistant.catalog.category_queryset", return_value=TicketCategory.objects.all()),
            patch.object(TicketCategory, "allowed_to_user", return_value=(True, "")) as allowed,
        ):
            self.client.get(URL, {
                "query": "password",
                "excluded_category_ids": [self.reset_password.id],
                "structure_ids": [self.ict.id],
            })

        allowed.assert_called_once_with(self.user)
        self.assertEqual(self.searched_ids(), {self.reset_2fa.id})

    # query senza testo, verifica se l'endpoint rifiuta la richiesta
    def test_missing_query_is_rejected(self):
        response = self.client.get(URL)

        self.assertEqual(response.status_code, 400)
        self.provider.embed_query.assert_not_called()

    # verifica se un utente non loggato viene bloccato
    def test_anonymous_user_is_rejected(self):
        response = APIClient().get(URL, {"query": "reset 2fa"})

        self.assertEqual(response.status_code, 401)
        self.provider.embed_query.assert_not_called()

    # verifica se ollama non viene chiamato se l'utente non ha categorie utilizzabili
    def test_no_available_categories_skips_ollama(self):
        self.available.return_value = []

        response = self.client.get(URL, {"query": "reset 2fa"})

        self.assertEqual(response.data, [])
        self.provider.embed_query.assert_not_called()

    # verifica se l'endpoint risponde in modo ordinato agli errori senz
    def test_search_failure_returns_503(self):
        self.provider.embed_query.side_effect = RuntimeError("Ollama spento")

        response = self.client.get(URL, {"query": "reset 2fa"})

        self.assertEqual(response.status_code, 503)
