"""Campi osservati, dati ignorati e cambiamenti dell’ufficio."""

from django.test import TestCase
from organizational_area.models import OrganizationalStructure, OrganizationalStructureOffice

from ..index_fields import INDEX_FIELDS, METADATA_FIELDS
from .helpers import CategoryTestsSetup


class UpdateNotificationTests(CategoryTestsSetup, TestCase):
    # Salva la categoria prima di osservare soltanto le sue modifiche.
    def setUp(self):
        super().setUp()
        with self.captureOnCommitCallbacks(execute=True):
            self.category = self.create_category()
        self.notifier.events.clear()

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

    # Questi salvataggi non modificano i campi osservati nel database.
    def test_ignored_changes_do_not_notify(self):
        cases = (
            ("invariato", {}, None),
            ("campo escluso", {"footer_text": "Solo stampa"}, ["footer_text"]),
            ("nome non salvato", {"name": "Solo in memoria"}, ["description"]),
            ("nessun campo salvato", {"name": "Ignorato"}, []),
        )
        for label, changes, fields in cases:
            with self.subTest(case=label):
                self.category.refresh_from_db()
                for field, value in changes.items():
                    setattr(self.category, field, value)
                with self.captureOnCommitCallbacks(execute=True) as callbacks:
                    self.category.save(update_fields=fields)
                self.assertEqual(callbacks, [])
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
