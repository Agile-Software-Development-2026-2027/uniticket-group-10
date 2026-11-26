"""API di aggiornamento singolo campo: modulo reale, stessa sicurezza della chat, nessun ticket creato."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from organizational_area.models import OrganizationalStructure
from rest_framework.test import APIClient
from uni_ticket.models import Ticket, TicketCategory, TicketCategoryInputList, TicketCategoryModule

URL = "/api/assistant/categories/{category_id}/form-fields/"


@override_settings(ROOT_URLCONF="assistant.urls")
class FormFieldUpdateAPITests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="field-update-user")
        self.client = APIClient()
        self.client.force_login(self.user)
        self.structure = OrganizationalStructure.objects.create(
            name="Field Update API", slug="field-update-api", unique_code="FIELD-UPDATE-API"
        )
        self.office = self.structure.get_default_office()
        self.category = TicketCategory.objects.create(
            name="Assistenza Wi-Fi",
            slug="field-update-wifi",
            description="Supporto nelle aule",
            is_active=True,
            organizational_structure=self.structure,
            organizational_office=self.office,
        )
        self.module = TicketCategoryModule.objects.create(
            name="Modulo attivo", ticket_category=self.category, is_active=True
        )
        TicketCategoryInputList.objects.create(
            category_module=self.module, name="Email", field_type="CustomEmailField"
        )
        TicketCategoryInputList.objects.create(
            category_module=self.module,
            name="Sede",
            field_type="CustomSelectBoxField",
            valore="Aula;Residenza",
            ordinamento=1,
        )
        form = self.module.get_form(show_conditions=True, current_user=self.user)
        self.subject, self.description, self.email, self.location = list(form.fields)
        self.url = URL.format(category_id=self.category.pk)

    def post(self, payload, client=None):
        return (client or self.client).post(self.url, payload, format="json")

    def test_valid_field_update_without_creating_ticket(self):
        response = self.post({"field_id": self.email, "value": "mario@unical.it"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"valid": True, "field_id": self.email, "value": "mario@unical.it", "errors": []},
        )
        self.assertEqual(Ticket.objects.count(), 0)

    def test_rejects_field_not_belonging_to_form(self):
        response = self.post({"field_id": "campo_inesistente", "value": "test"})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["valid"])
        self.assertEqual(response.json()["errors"][0]["code"], "unknown_field")

    def test_returns_validation_error_for_invalid_value(self):
        response = self.post({"field_id": self.location, "value": "Mensa"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["valid"])
        self.assertEqual(response.json()["errors"][0]["code"], "invalid_choice")

    def test_requires_authentication(self):
        with patch.object(TicketCategoryModule, "get_form") as get_form:
            response = self.post({"field_id": self.email, "value": "mario@unical.it"}, client=APIClient())
        self.assertEqual(response.status_code, 401)
        get_form.assert_not_called()

    def test_unavailable_category_returns_404(self):
        TicketCategory.objects.filter(pk=self.category.pk).update(is_active=False)
        response = self.post({"field_id": self.email, "value": "mario@unical.it"})
        self.assertEqual(response.status_code, 404)