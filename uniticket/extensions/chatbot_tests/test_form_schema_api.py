"""API dello schema: categorie reali e stessi criteri di accesso della chat."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from organizational_area.models import OrganizationalStructure
from rest_framework.test import APIClient
from uni_ticket.models import Ticket, TicketCategory, TicketCategoryInputList, TicketCategoryModule

from assistant.catalog import available_categories


URL = "/api/assistant/categories/{category_id}/form-schema/"


@override_settings(ROOT_URLCONF="assistant.urls")
class FormSchemaAPITests(TestCase):
    # Prepara una categoria accessibile con un modulo attivo e uno inattivo.
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="form-schema-user")
        self.client = APIClient()
        self.client.force_login(self.user)
        self.structure = OrganizationalStructure.objects.create(name="Schema API", slug="schema-api", unique_code="SCHEMA-API")
        self.office = self.structure.get_default_office()
        self.category = TicketCategory.objects.create(
            name="Assistenza Wi-Fi", slug="schema-wifi", description="Supporto nelle aule", is_active=True,
            organizational_structure=self.structure, organizational_office=self.office,
        )
        self.module = TicketCategoryModule.objects.create(name="Modulo attivo", ticket_category=self.category, is_active=True)
        TicketCategoryInputList.objects.create(category_module=self.module, name="Email", field_type="CustomEmailField")
        TicketCategoryInputList.objects.create(
            category_module=self.module, name="Note", field_type="CustomCharField", is_required=False, ordinamento=1,
        )
        TicketCategoryInputList.objects.create(
            category_module=self.module, name="Sede", field_type="CustomSelectBoxField",
            valore="Aula;Residenza", ordinamento=2,
        )
        old_module = TicketCategoryModule.objects.create(name="Modulo inattivo", ticket_category=self.category)
        TicketCategoryInputList.objects.create(category_module=old_module, name="Vecchio campo", field_type="CustomCharField")
        self.url = URL.format(category_id=self.category.pk)

    # Esegue davvero get_form() e restituisce il solo modulo attivo, senza creare ticket.
    def test_returns_active_form_schema(self):
        self.assertIn(self.category, available_categories(self.user))
        with patch.object(TicketCategoryModule, "get_form", autospec=True,
                          side_effect=TicketCategoryModule.get_form) as get_form:
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("application/json"))
        schema = response.json()
        self.assertEqual((schema["category_id"], schema["module_id"]), (self.category.pk, self.module.pk))
        subject, description, email, notes, location = schema["fields"]
        self.assertEqual([field["type"] for field in schema["fields"]], ["text", "text", "email", "text", "choice"])
        self.assertTrue(email["required"])
        self.assertFalse(notes["required"])
        self.assertEqual(subject["initial_value"], self.category.name)
        self.assertEqual(description["initial_value"], self.category.description)
        self.assertEqual(subject["constraints"]["max_length"], Ticket._meta.get_field("subject").max_length)
        self.assertIn({"value": "Aula", "label": "Aula"}, location["constraints"]["choices"])
        self.assertNotIn("html", subject)
        self.assertEqual(get_form.call_count, 1)
        self.assertEqual(get_form.call_args.args[0].pk, self.module.pk)
        self.assertEqual(get_form.call_args.kwargs, {"show_conditions": True, "current_user": self.user})
        self.assertEqual(Ticket.objects.count(), 0)

    # L'identità arriva dalla sessione: un utente anonimo non può leggere lo schema.
    def test_requires_authentication(self):
        with patch.object(TicketCategoryModule, "get_form") as get_form:
            response = APIClient().get(self.url)
        self.assertEqual(response.status_code, 401)
        get_form.assert_not_called()

    # Rifiuta gli stessi casi esclusi dal catalogo, prima di costruire il form.
    def test_reuses_chat_access_rules(self):
        now = timezone.now()
        cases = [
            (self.category, {"is_active": False}),
            (self.category, {"is_hidden": True}),
            (self.category, {"date_start": now + timedelta(days=1)}),
            (self.category, {"date_end": now - timedelta(days=1)}),
            (self.category, {"organizational_office_id": None}),
            (self.category, {"allow_anonymous": False, "allow_guest": False,
                             "allow_user": False, "allow_employee": False, "allow_spid_cie": False}),
            (self.office, {"is_active": False}),
            (self.structure, {"is_active": False}),
            (self.module, {"is_active": False}),
        ]
        for record, changes in cases:
            with self.subTest(model=type(record).__name__, changes=changes):
                records = type(record).objects.filter(pk=record.pk)
                previous = records.values(*changes).get()
                records.update(**changes)
                try:
                    self.assertNotIn(self.category, available_categories(self.user))
                    with patch.object(TicketCategoryModule, "get_form") as get_form:
                        response = self.client.get(self.url)
                    self.assertEqual(response.status_code, 404)
                    get_form.assert_not_called()
                finally:
                    records.update(**previous)

    # Gli ID inesistenti o malformati non fanno costruire alcun form.
    def test_invalid_category_ids(self):
        for category_id in [self.category.pk + 1000, 0, -1, 2**80, "abc"]:
            with self.subTest(category_id=category_id):
                with patch.object(TicketCategoryModule, "get_form") as get_form:
                    response = self.client.get(URL.format(category_id=category_id))
                self.assertEqual(response.status_code, 404)
                get_form.assert_not_called()

    # Non sceglie arbitrariamente un modulo se la categoria ne ha due attivi.
    def test_multiple_active_modules(self):
        TicketCategoryModule.objects.create(name="Altro modulo attivo", ticket_category=self.category, is_active=True)
        with patch.object(TicketCategoryModule, "get_form") as get_form:
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 409)
        get_form.assert_not_called()
