"""Prove del prototipo di prova: ogni scrittura attraversa una view originale."""
from io import StringIO

from django.core.management import call_command
from django.forms.models import model_to_dict
from django.test import Client, TestCase, override_settings
from django.urls import resolve, reverse
from uni_ticket.forms import CategoryForm
from uni_ticket.models import TicketCategory
from ticket_events.tests.helpers import CategoryTestsSetup


@override_settings(ROOT_URLCONF="receiver_lab.urls", RECEIVER_DEMO=True)
class PrototypeUITests(CategoryTestsSetup, TestCase):
    def setUp(self):
        super().setUp()
        call_command("prepare_receiver_lab", stdout=StringIO())

    def login(self):
        # Anche il login usa la view Django già configurata da UniTicket.
        response = self.client.post(reverse("login"), {
            "username": "receiver-manager", "password": "local-receivers-only",
            "next": "/receiver-lab/",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/receiver-lab/")

    def test_anonymous_page_explains_local_login_without_modifying_categories(self):
        response = self.client.get("/receiver-lab/")
        self.assertContains(response, "Prototipo locale")
        self.assertContains(response, 'action="/local/login/"')
        self.assertContains(response, "receiver-manager")
        self.assertFalse(TicketCategory.objects.exists())
        self.assertEqual(self.notifier.events, [])

    def test_prototype_uses_original_crud_for_full_round_trip(self):
        self.login()
        page = self.client.get("/receiver-lab/")
        create_url = page.context["create_url"]
        self.assertTrue(resolve(create_url).func.__module__.startswith("uni_ticket."))
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(create_url, {
                "name": "Prova dal prototipo", "description": "Supporto Wi-Fi", "max_requests_per_user": "0",
            })
        self.assertEqual(response.status_code, 302)
        category = TicketCategory.objects.get(slug="prova-dal-prototipo")
        self.assertEqual(self.notifier.events, [("CREATE", category.pk)])
        self.notifier.events.clear()
        page = self.client.get("/receiver-lab/")
        card = page.context["cards"][0]
        self.assertEqual(card["category"].pk, category.pk)
        values = model_to_dict(category, fields=CategoryForm.Meta.fields)
        values = {key: value if value is not None else "" for key, value in values.items()}
        values["description"] = "Supporto nelle aule"
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(card["edit_url"], values)
        self.assertEqual(response.status_code, 302)
        category.refresh_from_db()
        self.assertEqual(category.description, "Supporto nelle aule")
        self.assertEqual(self.notifier.events, [("UPDATE", category.pk)])
        self.notifier.events.clear()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(card["delete_url"])
        self.assertEqual(response.status_code, 302)
        self.assertFalse(TicketCategory.objects.filter(pk=category.pk).exists())
        self.assertEqual(self.notifier.events, [("DELETE", category.pk)])

    def test_prototype_view_rejects_writes(self):
        self.login()
        response = self.client.post("/receiver-lab/", {"name": "Non deve essere salvata"})
        self.assertEqual(response.status_code, 405)
        self.assertFalse(TicketCategory.objects.exists())
        self.assertEqual(self.notifier.events, [])

    def test_original_csrf_protection_remains_enabled(self):
        self.login()
        page = self.client.get("/receiver-lab/")
        protected_client = Client(enforce_csrf_checks=True)
        protected_client.cookies = self.client.cookies
        with self.captureOnCommitCallbacks(execute=True):
            response = protected_client.post(page.context["create_url"], {"name": "Senza token"})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(TicketCategory.objects.exists())
        self.assertEqual(self.notifier.events, [])

    @override_settings(RECEIVER_DEMO=False)
    def test_prototype_page_refuses_non_lab_settings(self):
        response = self.client.get("/receiver-lab/")
        self.assertEqual(response.status_code, 404)
