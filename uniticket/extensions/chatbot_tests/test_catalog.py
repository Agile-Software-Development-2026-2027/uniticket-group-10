"""Test di quello che l'agente riceve di ogni categoria: per chi è e i campi che la distinguono."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from organizational_area.models import OrganizationalStructure
from rest_framework.test import APIClient
from uni_ticket.models import TicketCategory, TicketCategoryInputList, TicketCategoryModule

from assistant.catalog import distinctive_field_labels

SEARCH_URL = "/api/assistant/search/"
CATEGORIES_URL = "/api/assistant/categories/"


@override_settings(ROOT_URLCONF="assistant.urls")
class CategoryCardTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="catalog-user")
        self.client = APIClient()
        self.client.force_login(self.user)
        self.structure = OrganizationalStructure.objects.create(name="Servizi Didattici", slug="sd", unique_code="SD")

        self.esonero = self.category("esonero", "Esonero IV rata", [
            "Matricola", "Altri componenti del nucleo familiare attualmente iscritti", "Oggetto della richiesta"])
        self.rimborso = self.category("rimborso", "Rimborso tasse", ["Matricola", "IBAN"])
        # "Matricola" è in quattro moduli: non distingue nessuno.
        self.category("certificato", "Certificato", ["Matricola"])
        self.category("piano", "Piano di studi", ["Matricola"])
        # Un campo nascosto non lo vede l'utente: non descrive il modulo.
        self.add_field(self.module_of(self.rimborso), "Codice interno", "CustomHiddenField")
        # Di un vecchio modulo non più attivo non conta nulla.
        old = TicketCategoryModule.objects.create(name="vecchio", ticket_category=self.esonero, is_active=False)
        self.add_field(old, "Campo di un modulo vecchio")

        patch("assistant.catalog.category_queryset", return_value=TicketCategory.objects.all()).start()
        self.addCleanup(patch.stopall)

    def category(self, slug, name, labels):
        category = TicketCategory.objects.create(
            name=name, slug=slug, organizational_structure=self.structure, allow_employee=False)
        module = TicketCategoryModule.objects.create(name=f"modulo {slug}", ticket_category=category, is_active=True)
        for label in labels:
            self.add_field(module, label)
        return category

    def module_of(self, category):
        return TicketCategoryModule.objects.get(ticket_category=category, is_active=True)

    def add_field(self, module, label, field_type="CustomCharField"):
        order = TicketCategoryInputList.objects.filter(category_module=module).count()
        TicketCategoryInputList.objects.create(
            category_module=module, name=label, field_type=field_type, ordinamento=order)

    def test_only_the_labels_that_distinguish_a_category_are_kept(self):
        labels = distinctive_field_labels([self.esonero, self.rimborso])

        self.assertEqual(labels, {
            self.esonero.pk: ["Altri componenti del nucleo familiare attualmente iscritti"],
            self.rimborso.pk: ["IBAN"],
        })

    def test_the_search_sends_who_a_category_is_for_and_its_distinctive_fields(self):
        with (
            patch("assistant.search.available_categories", return_value=[self.esonero]),
            patch("assistant.search.provider") as provider,
            patch("assistant.search.index_repository") as repository,
        ):
            provider.embed_query.return_value = [0.1]
            repository.search.return_value = [self.esonero.pk]
            response = self.client.get(SEARCH_URL, {"query": "esonero fratelli"})

        self.assertEqual(response.status_code, 200)
        [card] = response.data
        self.assertEqual(card["audience"], {"students": True, "staff": False, "guests": True, "anonymous": False})
        self.assertEqual(card["field_labels"], ["Altri componenti del nucleo familiare attualmente iscritti"])

    def test_the_list_of_categories_has_the_same_fields(self):
        with patch.object(TicketCategory, "allowed_to_user", return_value=(True, "")):
            response = self.client.get(CATEGORIES_URL)

        self.assertEqual(response.status_code, 200)
        by_name = {card["name"]: card for card in response.data}
        self.assertEqual(by_name["Rimborso tasse"]["field_labels"], ["IBAN"])
        self.assertEqual(by_name["Certificato"]["field_labels"], [])
