"""Assistant boundary tests against the same local fixture used by Compose."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import Client, TestCase, override_settings

from uni_ticket.models import Ticket


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
# TestCase usa un database di test: fixture e ticket creati non modificano i dati dell’ambiente locale.
class AssistantFlowTests(TestCase):
    fixtures = ["/dumps/local_conf.json"]

    # Ogni prova parte dall’utente normale della fixture locale, con sessione autenticata.
    def setUp(self):
        self.user = get_user_model().objects.get(username="utente")
        self.client.force_login(self.user)

    # Controlla accesso autenticato, metodi HTTP consentiti e identificatori non validi.
    def test_authentication_methods_and_invalid_category(self):
        self.assertEqual(Client().get("/assistant/form?ticket_id=316").status_code, 302)
        self.assertEqual(self.client.put("/assistant/form?ticket_id=316").status_code, 405)
        for query in ["", "?ticket_id=abc", "?ticket_id=99999999"]:
            with self.subTest(query=query):
                self.assertEqual(self.client.get("/assistant/form" + query).status_code, 404)

    # Le cinque tipologie devono produrre frammenti HTML, senza duplicare pagina o chat.
    def test_all_five_categories_return_only_the_form_panel(self):
        for category in [316, 317, 318, 319, 321]:
            with self.subTest(category=category):
                response = self.client.get(f"/assistant/form?ticket_id={category}")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["X-Assistant-Form"], "ready")
                self.assertEqual(response["Cache-Control"], "no-store")
                self.assertContains(response, 'id="chatbot-request-panel"', count=1)
                self.assertNotContains(response, "<!DOCTYPE", html=False)
                self.assertNotContains(response, 'id="chatbot-messages"')

    # Simula un diniego originale per verificare che l’estensione non lo trasformi in un form valido.
    def test_original_permission_response_is_preserved(self):
        with patch("assistant.views.TicketAddNew.get", return_value=HttpResponse("Denied", status=403)) as original:
            response = self.client.get("/assistant/form?ticket_id=316")
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("X-Assistant-Form", response)
        self.assertTrue(original.call_args.kwargs["api"])

    # Una POST incompleta deve conservare i dati e restituire errori, senza creare una richiesta.
    def test_invalid_post_returns_bound_form_without_creating_ticket(self):
        before = Ticket.objects.count()
        response = self.client.post("/assistant/form?ticket_id=316", {"ticket_subject": "Bozza mantenuta"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Assistant-Form"], "ready")
        self.assertContains(response, 'data-bound="true"')
        self.assertContains(response, "Bozza mantenuta")
        self.assertTrue(response.context["form"].errors)
        self.assertEqual(Ticket.objects.count(), before)

    # Le notifiche vengono simulate; validazione e creazione del ticket usano il codice originale.
    @patch("uni_ticket.views.user.send_custom_mail")
    @patch("uni_ticket.views.user.send_ticket_mail_to_operators")
    def test_valid_post_creates_one_ticket_and_returns_success_panel(self, operator_mail, owner_mail):
        payload = {
            "condizioni_field_id": "on", "ticket_subject": "Test assistant isolato",
            "ticket_description": "Dati sintetici", "il_sottoscritto_a_è_nato_a_a": "Comune di prova",
            "il": "2000-01-01", "cellulare": "3331234567", "email_personale": "test@example.invalid",
            "iscritto_per_l'a.a.": "2026/2027", "con_matricola": "123456",
            "al_corso_di_laurea_in": "Corso di prova",
            "il_rilascio_del_i_seguente_i_certificato_i": ["Iscrizione"], "confirm_submit": "Si, procedi",
        }
        before = Ticket.objects.count()
        # La chiave RSA non è configurata nella demo: il test verifica l’adattatore HTML simulando la cifratura.
        with patch("uni_ticket.views.user.encrypt_to_jwe", return_value="test-only-encrypted-data"):
            compiled = self.client.post("/assistant/form?ticket_id=316", {
                **payload, "confirm_submit": "", "generate_url_submit": "generate_url_submit",
            })
        self.assertContains(compiled, "id='encrypted_ticket_url'")
        self.assertEqual(Ticket.objects.count(), before)
        response = self.client.post("/assistant/form?ticket_id=316", payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-completed="true"')
        self.assertContains(response, "Apri il dettaglio della richiesta")
        self.assertEqual(Ticket.objects.count(), before + 1)
        self.assertEqual(Ticket.objects.get(subject="Test assistant isolato").created_by, self.user)
        self.assertEqual(response["X-Assistant-Form"], "ready")

    # Verifica sia il rifiuto senza CSRF sia il normale POST della pagina completa.
    def test_csrf_and_native_post_fallback(self):
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.user)
        self.assertEqual(csrf.post("/assistant/form?ticket_id=316", {}).status_code, 403)
        response = self.client.post("/assistant?ticket_id=316", {"ticket_subject": ""})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="chatbot-messages"')

    # Fissa il contratto della demo: chiarimento, lista vuota, cinque risultati e query non valida.
    def test_search_mock_contract(self):
        for query, key in [("dipartimento", "clarify"), ("no match", "tickets"), ("certificato", "tickets")]:
            with self.subTest(query=query):
                response = self.client.post("/api/search", {"query": query}, content_type="application/json")
                self.assertEqual(response.status_code, 200)
                self.assertIn(key, response.json())
                if query == "certificato":
                    self.assertEqual(len(response.json()[key]), 5)
                if query == "no match":
                    self.assertEqual(response.json()[key], [])
        self.assertEqual(self.client.post("/api/search", {"query": ""}, content_type="application/json").status_code, 400)
