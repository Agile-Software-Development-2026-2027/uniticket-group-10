"""TDD di UPDATE con notifier fittizio, modelli originali e database isolato."""

import logging

from django.db import transaction
from django.test import TestCase, TransactionTestCase, override_settings
from organizational_area.models import OrganizationalStructure, OrganizationalStructureOffice

from .index_fields import INDEX_FIELDS, METADATA_FIELDS
from .test_create_events import CreateTestsSetup


class UpdateTestsSetup(CreateTestsSetup):
    def setUp(self):
        super().setUp()
        # La preparazione conferma CREATE prima di osservare soltanto gli UPDATE.
        if isinstance(self, TestCase):
            with self.captureOnCommitCallbacks(execute=True):
                self.category = self.create_category()
        else:
            self.category = self.create_category()
        self.notifier.events.clear()


class UpdateNotificationTests(UpdateTestsSetup, TestCase):
    def test_each_index_field_triggers_update(self):
        other_structure = OrganizationalStructure.objects.create(
            name="Altra struttura", slug="other-update", unique_code="OTHER-UPDATE",
        )
        office = OrganizationalStructureOffice.objects.create(
            name="Ufficio", slug="office-update", organizational_structure=other_structure,
        )
        changed_values = {
            "name": "Nuovo nome",
            "description": "Nuova descrizione",
            "organizational_structure_id": other_structure.pk,
            "organizational_office_id": office.pk,
        }
        for field in METADATA_FIELDS:
            if field not in changed_values:
                changed_values[field] = not getattr(self.category, field)
        for field in INDEX_FIELDS:
            with self.subTest(field=field):
                self.notifier.events.clear()
                setattr(self.category, field, changed_values[field])
                with self.captureOnCommitCallbacks(execute=True):
                    self.category.save(update_fields=[field])
                self.assertEqual(self.notifier.events, [("UPDATE", self.category.pk)])

    def test_multiple_changes_produce_one_notification(self):
        self.category.name = "Nome aggiornato"
        self.category.is_active = True
        with self.captureOnCommitCallbacks(execute=True):
            self.category.save()
        self.assertEqual(self.notifier.events, [("UPDATE", self.category.pk)])

    def test_unchanged_save_does_not_notify(self):
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            self.category.save()
        self.assertEqual(callbacks, [])
        self.assertEqual(self.notifier.events, [])

    def test_excluded_field_does_not_notify(self):
        self.category.footer_text = "Nuovo testo di stampa"
        with self.captureOnCommitCallbacks(execute=True):
            self.category.save(update_fields=["footer_text"])
        self.assertEqual(self.notifier.events, [])

    def test_update_fields_ignores_unsaved_instance_changes(self):
        self.category.name = "Nome presente soltanto nell’istanza"
        with self.captureOnCommitCallbacks(execute=True):
            self.category.save(update_fields=["description"])
        self.assertEqual(self.notifier.events, [])
        self.category.refresh_from_db()
        self.assertEqual(self.category.name, "Categoria CREATE test")

    def test_null_and_empty_description_are_compared_as_saved(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.category.description = None
            self.category.save(update_fields=["description"])
        self.notifier.events.clear()
        with self.captureOnCommitCallbacks(execute=True):
            self.category.description = ""
            self.category.save(update_fields=["description"])
        self.assertEqual(self.notifier.events, [("UPDATE", self.category.pk)])

    def test_empty_update_fields_does_not_notify(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.category.name = "Ignorato"
            self.category.save(update_fields=[])
        self.assertEqual(self.notifier.events, [])

    def test_fixture_update_is_skipped(self):
        self.category.description = "Valore fixture"
        with self.captureOnCommitCallbacks(execute=True):
            self.category.save_base(raw=True)
        self.assertEqual(self.notifier.events, [])

    def test_waits_for_commit_and_keeps_category_id(self):
        original_id = self.category.pk
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            self.category.description = "Aggiornato"
            self.category.save(update_fields=["description"])
            self.assertEqual(self.notifier.events, [])
        self.assertEqual(len(callbacks), 1)
        self.category.pk = None
        callbacks[0]()
        self.assertEqual(self.notifier.events, [("UPDATE", original_id)])

    def test_notifier_failure_preserves_saved_values(self):
        def failing_notifier(operation, category_id):
            raise RuntimeError("Errore UPDATE simulato")

        with override_settings(TICKET_EVENTS_NOTIFIER=failing_notifier):
            with self.assertLogs("ticket_events", level=logging.ERROR) as logs:
                with self.captureOnCommitCallbacks(execute=True):
                    self.category.description = "Modifica confermata"
                    self.category.save(update_fields=["description"])
        self.category.refresh_from_db()
        self.assertEqual(self.category.description, "Modifica confermata")
        self.assertIn("UPDATE", logs.output[0])
        self.assertIn(str(self.category.pk), logs.output[0])
        self.assertIsNotNone(logs.records[0].exc_info)

    def test_renaming_structure_and_office_does_not_notify(self):
        office = OrganizationalStructureOffice.objects.create(
            name="Ufficio iniziale", slug="rename-test", organizational_structure=self.structure,
        )
        with self.captureOnCommitCallbacks(execute=True):
            self.category.organizational_office = office
            self.category.save(update_fields=["organizational_office"])
        self.notifier.events.clear()
        with self.captureOnCommitCallbacks(execute=True):
            self.structure.name = "Struttura rinominata"
            self.structure.save(update_fields=["name"])
            office.name = "Ufficio rinominato"
            office.save(update_fields=["name"])
        self.assertEqual(self.notifier.events, [])

    def test_same_named_office_reassignment_updates_metadata(self):
        office_one = OrganizationalStructureOffice.objects.create(
            name="Stesso nome", slug="one-update", organizational_structure=self.structure,
        )
        office_two = OrganizationalStructureOffice.objects.create(
            name="Stesso nome", slug="two-update", organizational_structure=self.structure,
        )
        with self.captureOnCommitCallbacks(execute=True):
            self.category.organizational_office = office_one
            self.category.save(update_fields=["organizational_office"])
        self.notifier.events.clear()
        with self.captureOnCommitCallbacks(execute=True):
            self.category.organizational_office = office_two
            self.category.save(update_fields=["organizational_office"])
        self.assertEqual(self.notifier.events, [("UPDATE", self.category.pk)])

    def test_office_deletion_notifies_set_null(self):
        office = OrganizationalStructureOffice.objects.create(
            name="Ufficio eliminabile", slug="delete-update", organizational_structure=self.structure,
        )
        with self.captureOnCommitCallbacks(execute=True):
            self.category.organizational_office = office
            self.category.save(update_fields=["organizational_office"])
        self.notifier.events.clear()
        with self.captureOnCommitCallbacks(execute=True):
            office.delete()
        self.category.refresh_from_db()
        self.assertIsNone(self.category.organizational_office_id)
        self.assertEqual(self.notifier.events, [("UPDATE", self.category.pk)])

    def test_queryset_update_bypasses_model_signals(self):
        with self.captureOnCommitCallbacks(execute=True):
            type(self.category).objects.filter(pk=self.category.pk).update(description="SQL diretto")
        self.assertEqual(self.notifier.events, [])

    @override_settings(RECEIVER_DEMO=True, ROOT_URLCONF="ticket_events.demo_urls")
    def test_demo_can_change_boolean_metadata(self):
        with self.captureOnCommitCallbacks(execute=True):
            created = self.client.post("/api/categories/", data={
                "name": "Categoria demo UPDATE", "description": "Prova",
            }, content_type="application/json")
        category_id = created.json()["id"]
        self.notifier.events.clear()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.put(f"/api/categories/{category_id}/", data={
                "name": "Categoria demo UPDATE", "description": "Prova", "is_active": True,
            }, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["metadata"]["is_active"])
        self.assertEqual(self.notifier.events, [("UPDATE", category_id)])

    @override_settings(RECEIVER_DEMO=True, ROOT_URLCONF="ticket_events.demo_urls")
    def test_demo_rejects_non_boolean_metadata(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post("/api/categories/", data={
                "name": "Categoria non valida", "description": "Prova", "is_active": "false",
            }, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.notifier.events, [])


class UpdateTransactionTests(UpdateTestsSetup, TransactionTestCase):
    def test_real_commit_delivers_update(self):
        with transaction.atomic():
            self.category.description = "Confermato"
            self.category.save(update_fields=["description"])
            self.assertEqual(self.notifier.events, [])
        self.assertEqual(self.notifier.events, [("UPDATE", self.category.pk)])

    def test_rollback_discards_update(self):
        with self.assertRaises(ValueError):
            with transaction.atomic():
                self.category.description = "Da annullare"
                self.category.save(update_fields=["description"])
                raise ValueError("Rollback UPDATE")
        self.category.refresh_from_db()
        self.assertEqual(self.category.description, "Descrizione di prova")
        self.assertEqual(self.notifier.events, [])

    def test_autocommit_notifies_update_immediately(self):
        self.category.description = "Autocommit"
        self.category.save(update_fields=["description"])
        self.assertEqual(self.notifier.events, [("UPDATE", self.category.pk)])
