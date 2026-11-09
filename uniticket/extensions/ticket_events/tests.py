"""Real ORM and commit callbacks; database and attachment paths are isolated."""
import json
import logging
from pathlib import Path
from django.conf import settings
from django.db import connection, transaction
from django.test import TransactionTestCase
from organizational_area.models import OrganizationalStructure, OrganizationalStructureOffice
from uni_ticket.models import TicketCategory

class Collector(logging.Handler):
    def __init__(self):
        super().__init__()
        self.events = []
    def emit(self, record):
        message = record.getMessage()
        if message.startswith("[TICKET EVENT] {"):
            self.events.append(json.loads(message[len("[TICKET EVENT] "):]))

class ContentEventsTests(TransactionTestCase):
    @staticmethod
    def differences(event):
        return {field: {"before": event["before"][field], "after": value}
                for field, value in event["after"].items()
                if event["before"][field] != value}

    def setUp(self):
        self.assertTrue(getattr(settings, "TICKET_EVENTS_ISOLATED_TEST", False))
        self.assertEqual(connection.vendor, "sqlite")
        self.assertIn("memory", str(connection.settings_dict["NAME"]))
        self.assertTrue(Path(settings.MEDIA_ROOT).resolve().is_relative_to(Path(settings.TICKET_EVENTS_TEST_ROOT).resolve()))
        self.collector = Collector()
        logger = logging.getLogger("ticket_events")
        logger.addHandler(self.collector)
        self.addCleanup(logger.removeHandler, self.collector)
        self.structure = OrganizationalStructure.objects.create(name="Struttura test", slug="test", unique_code="test")
        self.office = OrganizationalStructureOffice.objects.create(name="Ufficio test", slug="test", organizational_structure=self.structure)

    def create_category(self, slug="category"):
        return TicketCategory.objects.create(name="Servizio test", slug=slug, description="Prima",
            organizational_structure=self.structure, organizational_office=self.office)

    def test_create_update_unchanged_and_delete(self):
        category = self.create_category()
        self.assertEqual(self.collector.events[-1]["operation"], "CREATE")
        category.description = "Dopo"
        category.save(update_fields=["description"])
        self.assertEqual(self.differences(self.collector.events[-1]), {"description": {"before": "Prima", "after": "Dopo"}})
        category.save(update_fields=["description"])
        self.assertEqual(self.collector.events[-1]["possible_action"], "NONE")
        category_id = category.pk
        folder = (Path(settings.MEDIA_ROOT) / category.get_folder()).resolve()
        self.assertTrue(folder.is_relative_to(Path(settings.MEDIA_ROOT).resolve()))
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "dummy.txt").write_text("test")
        category.delete()
        self.assertEqual(self.collector.events[-1]["possible_action"], "REMOVE")
        self.assertEqual(self.collector.events[-1]["category_id"], category_id)
        self.assertFalse(folder.exists())

    def test_ignored_fields_and_unsaved_values(self):
        category = self.create_category()
        category.name = "Not persisted"
        category.is_active = True
        category.save(update_fields=["is_active"])
        self.assertEqual(self.collector.events[-1]["possible_action"], "NONE")

    def test_structure_rename_updates_all_linked_categories(self):
        ids = {self.create_category("one").pk, self.create_category("two").pk}
        self.collector.events.clear()
        self.structure.name = "Struttura nuova"
        self.structure.save(update_fields=["name"])
        self.assertEqual({event["category_id"] for event in self.collector.events}, ids)
        for event in self.collector.events:
            self.assertEqual(self.differences(event), {"organizational_structure.name": {"before": "Struttura test", "after": "Struttura nuova"}})

    def test_office_rename_and_unrelated_update(self):
        self.create_category()
        self.office.name = "Ufficio nuovo"
        self.office.save(update_fields=["name"])
        self.assertEqual(self.differences(self.collector.events[-1]), {"organizational_office.name": {"before": "Ufficio test", "after": "Ufficio nuovo"}})
        self.collector.events.clear()
        self.office.description = "Non incluso"
        self.office.save(update_fields=["description"])
        self.assertEqual(self.collector.events, [])

    def test_assign_remove_and_delete_office(self):
        category = self.create_category()
        category.organizational_office = None
        category.save(update_fields=["organizational_office"])
        self.assertEqual(self.differences(self.collector.events[-1])["organizational_office.name"]["after"], "")
        category.organizational_office = self.office
        category.save(update_fields=["organizational_office"])
        self.assertEqual(self.collector.events[-1]["possible_action"], "REINDEX")
        self.collector.events.clear()
        self.office.delete()
        category.refresh_from_db()
        self.assertIsNone(category.organizational_office_id)
        self.assertEqual(len(self.collector.events), 1)
        self.assertEqual(self.collector.events[0]["signal"], "post_delete")
        self.assertEqual(self.collector.events[0]["possible_action"], "REINDEX")

    def test_commit_and_rollback(self):
        category = self.create_category()
        self.collector.events.clear()
        with transaction.atomic():
            category.description = "Committed"
            category.save(update_fields=["description"])
            self.assertEqual(self.collector.events, [])
        self.assertEqual(len(self.collector.events), 1)
        self.collector.events.clear()
        with self.assertRaises(ValueError):
            with transaction.atomic():
                category.description = "Rolled back"
                category.save(update_fields=["description"])
                raise ValueError("rollback")
        self.assertEqual(self.collector.events, [])
        category.refresh_from_db()
        self.assertEqual(category.description, "Committed")

    def test_reassign_same_named_office_does_not_change_text(self):
        category = self.create_category()
        other = OrganizationalStructureOffice.objects.create(name=self.office.name, slug="other", organizational_structure=self.structure)
        category.organizational_office = other
        category.save(update_fields=["organizational_office"])
        self.assertEqual(self.collector.events[-1]["possible_action"], "NONE")
