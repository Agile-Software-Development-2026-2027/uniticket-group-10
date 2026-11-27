"""API di validazione: modulo reale, stessi criteri di accesso della chat, nessun ticket creato."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from organizational_area.models import OrganizationalStructure
from rest_framework.test import APIClient
from uni_ticket.models import Ticket, TicketCategory, TicketCategoryInputList, TicketCategoryModule


URL = "/api/assistant/categories/{category_id}/form-validation/"


@override_settings(ROOT_URLCONF="assistant.urls")
class FormValidationAPITests(TestCase):
    # Stessa categoria dei test dello schema: email obbligatoria, note facoltative, sede a scelta
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="form-validation-user")
        self.client = APIClient()
        self.client.force_login(self.user)
        self.structure = OrganizationalStructure.objects.create(
            name="Validation API", slug="validation-api", unique_code="VALIDATION-API")
        self.office = self.structure.get_default_office()
        self.category = TicketCategory.objects.create(
            name="Assistenza Wi-Fi", slug="validation-wifi", description="Supporto nelle aule", is_active=True,
            organizational_structure=self.structure, organizational_office=self.office,
        )
        self.module = TicketCategoryModule.objects.create(
            name="Modulo attivo", ticket_category=self.category, is_active=True)
        TicketCategoryInputList.objects.create(category_module=self.module, name="Email", field_type="CustomEmailField")
        TicketCategoryInputList.objects.create(
            category_module=self.module, name="Note", field_type="CustomCharField", is_required=False, ordinamento=1,
        )
        TicketCategoryInputList.objects.create(
            category_module=self.module, name="Sede", field_type="CustomSelectBoxField",
            valore="Aula;Residenza", ordinamento=2,
        )
        # Gli ID dei campi li prendiamo dal form vero, gli stessi dello schema
        form = self.module.get_form(show_conditions=True, current_user=self.user)
        self.subject, self.description, self.email, self.notes, self.location = list(form.fields)
        self.url = URL.format(category_id=self.category.pk)

    def post(self, data, client=None):
        return (client or self.client).post(self.url, {"data": data}, format="json")

    def valid_data(self):
        return {
            self.subject: "Wi-Fi non funziona",
            self.description: "Non riesco a collegarmi in aula",
            self.email: "mario@unical.it",
            self.location: "Aula",
        }

    # Dati corretti: form valido, get_form chiamato senza allegati e nessun ticket creato
    def test_valid_data(self):
        with patch.object(TicketCategoryModule, "get_form", autospec=True,
                          side_effect=TicketCategoryModule.get_form) as get_form:
            response = self.post(self.valid_data())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"valid": True, "missing_fields": [], "errors": []})
        self.assertEqual(get_form.call_count, 1)
        self.assertEqual(get_form.call_args.args[0].pk, self.module.pk)
        self.assertTrue(get_form.call_args.kwargs["remove_filefields"])
        self.assertEqual(Ticket.objects.count(), 0)

    # Campi mancanti e valori sbagliati vengono separati
    def test_missing_and_invalid_fields(self):
        response = self.post({self.email: "mario@", self.location: "Mensa"})
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertFalse(result["valid"])
        self.assertEqual(sorted(result["missing_fields"]), sorted([self.subject, self.description]))
        codes = {error["field"]: error["code"] for error in result["errors"]}
        self.assertEqual(codes, {self.email: "invalid", self.location: "invalid_choice"})
        self.assertEqual(Ticket.objects.count(), 0)

    # Senza sessione l'utente è anonimo e il form non viene costruito
    def test_requires_authentication(self):
        with patch.object(TicketCategoryModule, "get_form") as get_form:
            response = self.post(self.valid_data(), client=APIClient())
        self.assertEqual(response.status_code, 401)
        get_form.assert_not_called()

    # L'agente non ha il token CSRF: la richiesta JSON con la sola sessione deve passare
    def test_does_not_require_csrf(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = self.post(self.valid_data(), client=client)
        self.assertEqual(response.status_code, 200)

    # Solo JSON: un form HTML viene rifiutato
    def test_accepts_only_json(self):
        response = self.client.post(self.url, {"data": "x"})
        self.assertEqual(response.status_code, 415)

    # Il body deve contenere "data" come dizionario
    def test_invalid_body(self):
        for body in [{}, {"data": "ciao"}, {"data": [1, 2]}]:
            with self.subTest(body=body):
                with patch.object(TicketCategoryModule, "get_form") as get_form:
                    response = self.client.post(self.url, body, format="json")
                self.assertEqual(response.status_code, 400)
                get_form.assert_not_called()

    # Categoria non accessibile o inesistente: 404 prima di costruire il form
    def test_unavailable_categories(self):
        TicketCategory.objects.filter(pk=self.category.pk).update(is_active=False)
        for category_id in [self.category.pk, self.category.pk + 1000]:
            with self.subTest(category_id=category_id):
                with patch.object(TicketCategoryModule, "get_form") as get_form:
                    response = self.client.post(
                        URL.format(category_id=category_id), {"data": {}}, format="json")
                self.assertEqual(response.status_code, 404)
                get_form.assert_not_called()

    # Due moduli attivi: non ne sceglie uno a caso
    def test_multiple_active_modules(self):
        TicketCategoryModule.objects.create(name="Altro modulo attivo", ticket_category=self.category, is_active=True)
        with patch.object(TicketCategoryModule, "get_form") as get_form:
            response = self.post(self.valid_data())
        self.assertEqual(response.status_code, 409)
        get_form.assert_not_called()