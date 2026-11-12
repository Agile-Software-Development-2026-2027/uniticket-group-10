"""Integrazione HTTP: URL, form, permessi e modelli originali UniTicket."""

from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.forms.models import model_to_dict
from django.test import TestCase
from django.urls import resolve, reverse
from organizational_area.models import (
    OrganizationalStructureOffice,
    OrganizationalStructureOfficeEmployee,
    UserManageOrganizationalStructure,
)
from uni_ticket.forms import CategoryForm
from uni_ticket.models import Ticket, TicketCategory, TicketCategoryModule
from extensions import settings as original_settings

from ..interfaces import CategoryOperation
from .helpers import CategoryTestsSetup


class OfficialCategoryViewTests(CategoryTestsSetup, TestCase):
    def setUp(self):
        super().setUp()
        # Il manager ottiene i permessi tramite le relazioni originali, senza mock.
        self.manager = get_user_model().objects.create_user(
            username="receiver-manager", password="local-test-only",
            first_name="Manager", last_name="Test", is_staff=True,
        )
        UserManageOrganizationalStructure.objects.create(
            user=self.manager, organizational_structure=self.structure,
        )
        OrganizationalStructureOfficeEmployee.objects.create(
            employee=self.manager, office=self.structure.get_default_office(),
        )
        self.client.force_login(self.manager)
        with self.captureOnCommitCallbacks(execute=True):
            self.category = self.create_category()
        self.notifier.events.clear()

    def url(self, name, category=None, **kwargs):
        parameters = {"structure_slug": self.structure.slug, **kwargs}
        if category is not None:
            parameters["category_slug"] = category.slug
        # reverse e resolve attraversano il ROOT_URLCONF originale, non URL di prova.
        url = reverse("uni_ticket:" + name, kwargs=parameters)
        self.assertTrue(resolve(url).func.__module__.startswith("uni_ticket."))
        return url

    def payload(self, **changes):
        # Il POST ripresenta i campi del form originale, preservando i flag esistenti.
        fields = CategoryForm.Meta.fields
        values = model_to_dict(self.category, fields=fields)
        values = {key: value if value is not None else "" for key, value in values.items()}
        values.update(changes)
        return values

    def office(self, slug="official-office"):
        return OrganizationalStructureOffice.objects.create(
            name="Ufficio di prova", slug=slug, organizational_structure=self.structure,
            is_active=True,
        )

    def assign_office(self, office, active=False):
        with self.captureOnCommitCallbacks(execute=True):
            self.category.organizational_office = office
            self.category.is_active = active
            self.category.save(update_fields=["organizational_office", "is_active"])
        self.notifier.events.clear()


    def test_original_create_reaches_receiver(self):
        url = self.url("manager_category_add_new")
        response = self.post_and_commit(url, self.payload(name="Nuova tipologia ufficiale"))
        self.assertEqual(response.status_code, 302)
        category = TicketCategory.objects.get(slug="nuova-tipologia-ufficiale")
        self.assertEqual(category.organizational_structure_id, self.structure.pk)
        self.assertEqual(self.notifier.events, [(CategoryOperation.CREATE, category.pk)])

    # Ogni campo del form viene modificato separatamente.
    def test_original_edit_detects_text_and_access_flags(self):
        changes = {"name": "Nuovo servizio", "description": "Supporto nelle aule"}
        for field in ("allow_user", "allow_employee", "allow_anonymous", "allow_guest", "allow_spid_cie"):
            changes[field] = not getattr(self.category, field)
        for field, value in changes.items():
            with self.subTest(field=field):
                self.notifier.events.clear()
                response = self.post_and_commit(
                    self.url("manager_category_edit", self.category),
                    self.payload(**{field: value}),
                )
                self.assertEqual(response.status_code, 302)
                self.category.refresh_from_db()
                self.assertEqual(getattr(self.category, field), value)
                self.assertEqual(self.notifier.events, [(CategoryOperation.UPDATE, self.category.pk)])


    def test_original_edit_ignores_unchanged_and_excluded_fields(self):
        for changes in ({}, {"footer_text": "Solo testo di stampa"}):
            with self.subTest(changes=changes):
                response = self.post_and_commit(
                    self.url("manager_category_edit", self.category), self.payload(**changes),
                )
                self.assertEqual(response.status_code, 302)
                self.category.refresh_from_db()
                self.assertEqual(self.notifier.events, [])

    # Nomi invalidi e duplicati non devono salvare dati o emettere notifiche.
    def test_original_forms_reject_invalid_and_duplicate_names(self):
        before = TicketCategory.objects.count()
        cases = (
            ("manager_category_add_new", None, {"name": "123"}, True),
            ("manager_category_add_new", None, {}, False),
            ("manager_category_edit", self.category, {"name": "123"}, True),
        )
        for view, category, changes, form_errors in cases:
            with self.subTest(view=view, changes=changes):
                response = self.post_and_commit(self.url(view, category), self.payload(**changes))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(bool(response.context["form"].errors), form_errors)
                self.assertEqual(TicketCategory.objects.count(), before)
                self.category.refresh_from_db()
                self.assertEqual(self.category.name, "Categoria CREATE test")
                self.assertEqual(self.notifier.events, [])


    def test_anonymous_crud_is_blocked_without_events(self):
        self.client.logout()
        for name in ("manager_category_add_new", "manager_category_edit", "manager_delete_category"):
            with self.subTest(view=name):
                category = None if name == "manager_category_add_new" else self.category
                response = self.post_and_commit(self.url(name, category), self.payload(name="Non consentito"))
                self.assertEqual(response.status_code, 302)
                self.assertIn("login", response.url)
                self.assertEqual(self.notifier.events, [])
        self.category.refresh_from_db()
        self.assertEqual(self.category.name, "Categoria CREATE test")

    def test_user_without_manager_permissions_cannot_modify_category(self):
        user = get_user_model().objects.create_user(username="not-manager")
        self.client.force_login(user)
        response = self.post_and_commit(
            self.url("manager_category_edit", self.category), self.payload(name="Non consentito"),
        )
        self.assertEqual(response.status_code, 200)
        self.category.refresh_from_db()
        self.assertEqual(self.category.name, "Categoria CREATE test")
        self.assertEqual(self.notifier.events, [])

    def test_detail_get_does_not_modify_or_notify(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.get(self.url("manager_category_detail", self.category))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.notifier.events, [])

    def test_original_enable_and_disable_reach_receiver(self):
        self.assign_office(self.office())
        # L’attivazione originale richiede un modulo attivo: la regola non è aggirata.
        TicketCategoryModule.objects.create(name="Modulo locale", ticket_category=self.category, is_active=True)
        for name, expected in (("manager_enable_category", True), ("manager_disable_category", False)):
            with self.subTest(view=name):
                self.notifier.events.clear()
                response = self.post_and_commit(self.url(name, self.category))
                self.assertEqual(response.status_code, 302)
                self.category.refresh_from_db()
                self.assertEqual(self.category.is_active, expected)
                self.assertEqual(self.notifier.events, [(CategoryOperation.UPDATE, self.category.pk)])

    def test_original_enable_blocked_without_office_does_not_notify(self):
        response = self.post_and_commit(self.url("manager_enable_category", self.category))
        self.assertEqual(response.status_code, 302)
        self.category.refresh_from_db()
        self.assertFalse(self.category.is_active)
        self.assertEqual(self.notifier.events, [])

    def test_original_office_assignment_from_both_views(self):
        office = self.office()
        for name in ("manager_category_detail", "manager_add_office_category"):
            with self.subTest(view=name):
                # Ogni percorso parte da una categoria realmente priva di ufficio.
                self.assign_office(None)
                if name == "manager_category_detail":
                    url = self.url(name, self.category)
                    data = {"office": office.slug}
                else:
                    url = self.url(name, office_slug=office.slug)
                    data = {"category": self.category.slug}
                response = self.post_and_commit(url, data)
                self.assertEqual(response.status_code, 302)
                self.category.refresh_from_db()
                self.assertEqual(self.category.organizational_office_id, office.pk)
                self.assertEqual(self.notifier.events, [(CategoryOperation.UPDATE, self.category.pk)])

    def test_original_office_removal_from_both_views(self):
        office = self.office()
        for name in ("manager_remove_category_office", "manager_remove_office_category"):
            with self.subTest(view=name):
                self.assign_office(office, active=True)
                response = self.post_and_commit(self.url(name, self.category, office_slug=office.slug))
                self.assertEqual(response.status_code, 302)
                self.category.refresh_from_db()
                self.assertIsNone(self.category.organizational_office_id)
                self.assertFalse(self.category.is_active)
                self.assertEqual(self.notifier.events, [(CategoryOperation.UPDATE, self.category.pk)])

    def test_original_office_delete_updates_all_surviving_categories(self):
        office = self.office()
        self.assign_office(office, active=True)
        with self.captureOnCommitCallbacks(execute=True):
            second = self.create_category(slug="second-category", name="Seconda categoria", organizational_office=office)
        self.notifier.events.clear()
        response = self.post_and_commit(self.url("manager_delete_office", office_slug=office.slug))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(OrganizationalStructureOffice.objects.filter(pk=office.pk).exists())
        self.category.refresh_from_db()
        second.refresh_from_db()
        self.assertIsNone(self.category.organizational_office_id)
        self.assertIsNone(second.organizational_office_id)
        # La view disattiva prima la categoria attiva, poi SET_NULL modifica l’ufficio.
        self.assertEqual(self.notifier.events.count((CategoryOperation.UPDATE, self.category.pk)), 2)
        self.assertEqual(self.notifier.events.count((CategoryOperation.UPDATE, second.pk)), 1)
        self.assertEqual(len(self.notifier.events), 3)

    def test_original_crud_rollback_discards_receiver_callbacks(self):
        cases = (
            ("manager_category_add_new", None, self.payload(name="Creazione annullata")),
            ("manager_category_edit", self.category, self.payload(description="Modifica annullata")),
            ("manager_delete_category", self.category, {}),
        )
        for name, category, data in cases:
            with self.subTest(view=name):
                with self.captureOnCommitCallbacks(execute=True) as callbacks:
                    with self.assertRaisesRegex(ValueError, "rollback locale"):
                        with transaction.atomic():
                            response = self.client.post(self.url(name, category), data)
                            self.assertEqual(response.status_code, 302)
                            raise ValueError("rollback locale")
                self.assertEqual(callbacks, [])
                self.assertEqual(self.notifier.events, [])
                self.category.refresh_from_db()
                self.assertEqual(self.category.description, "Descrizione di prova")
                self.assertFalse(TicketCategory.objects.filter(slug="creazione-annullata").exists())

    # La configurazione registra l’app una volta; ready ripetuto non duplica i receiver.
    def test_app_registration_does_not_duplicate_receivers(self):
        app = "ticket_events.apps.TicketEventsConfig"
        self.assertEqual(original_settings.INSTALLED_APPS.count(app), 1)
        self.assertTrue(apps.is_installed("ticket_events"))
        app_config = apps.get_app_config("ticket_events")
        app_config.ready()
        app_config.ready()
        response = self.post_and_commit(
            self.url("manager_category_edit", self.category), self.payload(description="Un solo evento"),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.notifier.events, [(CategoryOperation.UPDATE, self.category.pk)])

    def test_original_office_delete_rollback_preserves_links_without_events(self):
        office = self.office()
        self.assign_office(office, active=True)
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            with self.assertRaisesRegex(ValueError, "rollback ufficio"):
                with transaction.atomic():
                    response = self.client.post(self.url("manager_delete_office", office_slug=office.slug))
                    self.assertEqual(response.status_code, 302)
                    raise ValueError("rollback ufficio")
        self.category.refresh_from_db()
        self.assertTrue(OrganizationalStructureOffice.objects.filter(pk=office.pk).exists())
        self.assertEqual(self.category.organizational_office_id, office.pk)
        self.assertTrue(self.category.is_active)
        self.assertEqual(callbacks, [])
        self.assertEqual(self.notifier.events, [])


    def test_original_delete_of_used_category_is_blocked_without_event(self):
        module = TicketCategoryModule.objects.create(name="Modulo utilizzato", ticket_category=self.category)
        # La richiesta esiste soltanto per esercitare il vincolo originale di cancellazione.
        Ticket.objects.create(
            subject="Richiesta di test", description="Dato temporaneo", input_module=module,
            created_by=self.manager,
        )
        response = self.post_and_commit(self.url("manager_delete_category", self.category))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(TicketCategory.objects.filter(pk=self.category.pk).exists())
        self.assertEqual(self.notifier.events, [])

    def test_original_attachment_cleanup_remains_registered(self):
        # get_folder() è relativo: il receiver originale antepone MEDIA_ROOT.
        folder = (Path(settings.MEDIA_ROOT) / self.category.get_folder()).resolve()
        # Anche la pulizia originale deve operare esclusivamente nei file temporanei dei test.
        self.assertTrue(folder.is_relative_to(Path(settings.TICKET_EVENTS_TEST_ROOT).resolve()))
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "attachment.txt").write_text("allegato temporaneo", encoding="utf-8")
        response = self.post_and_commit(self.url("manager_delete_category", self.category))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(folder.exists())
        self.assertFalse(TicketCategory.objects.filter(pk=self.category.pk).exists())
        self.assertEqual(self.notifier.events, [(CategoryOperation.DELETE, self.category.pk)])
