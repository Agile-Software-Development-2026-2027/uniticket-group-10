"""Messaggi semplici dei receiver con signals reali e dati temporanei."""
import json
from django.test import TestCase, override_settings
from organizational_area.models import OrganizationalStructureOffice
from .helpers import CategoryTestsSetup
from ..index_fields import INDEX_FIELDS


@override_settings(TICKET_EVENTS_NOTIFIER="ticket_events.notifications.log_notification")
class ReceiverMessageTests(CategoryTestsSetup, TestCase):
    def setUp(self):
        super().setUp()
        # Il test verifica il destinatario di log, sostituendo soltanto il fake condiviso.
        configured = override_settings(TICKET_EVENTS_NOTIFIER="ticket_events.notifications.log_notification")
        configured.enable()
        self.addCleanup(configured.disable)

    def event(self, records):
        messages = [record.getMessage() for record in records if record.getMessage().startswith("[TICKET EVENT] ")]
        self.assertEqual(len(messages), 1)
        return json.loads(messages[0].removeprefix("[TICKET EVENT] "))

    def test_create_message_explains_signal_category_and_possible_action(self):
        with self.assertLogs("ticket_events", level="INFO") as logs:
            with self.captureOnCommitCallbacks(execute=True):
                category = self.create_category()
        event = self.event(logs.records)
        self.assertEqual(event["signal"], "post_save")
        self.assertEqual(event["source_model"], "TicketCategory")
        self.assertEqual(event["category_id"], category.pk)
        self.assertEqual(event["operation"], "CREATE")
        self.assertEqual(event["possible_action"], "INDEX")
        self.assertIsNone(event["before"])
        self.assertEqual(event["after"]["name"], category.name)

    def test_update_message_preserves_full_content_and_unchanged_metadata(self):
        with self.captureOnCommitCallbacks(execute=True):
            category = self.create_category()
        with self.assertLogs("ticket_events", level="INFO") as logs:
            with self.captureOnCommitCallbacks(execute=True):
                category.description = "Supporto nelle aule"
                category.save(update_fields=["description"])
        event = self.event(logs.records)
        self.assertEqual(event["possible_action"], "REINDEX")
        self.assertEqual(set(event["before"]), set(INDEX_FIELDS))
        self.assertEqual(set(event["after"]), set(INDEX_FIELDS))
        self.assertEqual(event["before"]["description"], "Descrizione di prova")
        self.assertEqual(event["after"]["description"], "Supporto nelle aule")
        # Cambiare solo il testo deve conservare nel messaggio anche i metadata invariati.
        self.assertEqual(event["after"]["name"], category.name)
        self.assertEqual(event["after"]["organizational_structure_id"], self.structure.pk)
        self.assertIsNone(event["after"]["organizational_office_id"])
        self.assertTrue(event["after"]["allow_user"])
        for field in INDEX_FIELDS:
            if field != "description":
                self.assertEqual(event["before"][field], event["after"][field])

    @override_settings(RECEIVER_DEMO=True)
    def test_unchanged_save_is_reported_as_none_in_lab_only(self):
        with self.captureOnCommitCallbacks(execute=True):
            category = self.create_category()
        with self.assertLogs("ticket_events", level="INFO") as logs:
            with self.captureOnCommitCallbacks(execute=True):
                category.save()
        event = self.event(logs.records)
        self.assertEqual(event["operation"], "UPDATE")
        self.assertEqual(event["possible_action"], "NONE")
        self.assertEqual(set(event["after"]), set(INDEX_FIELDS))
        self.assertEqual(event["before"], event["after"])

    def test_delete_message_preserves_previous_values(self):
        with self.captureOnCommitCallbacks(execute=True):
            category = self.create_category()
        category_id = category.pk
        with self.assertLogs("ticket_events", level="INFO") as logs:
            with self.captureOnCommitCallbacks(execute=True):
                category.delete()
        event = self.event(logs.records)
        self.assertEqual(event["signal"], "post_delete")
        self.assertEqual(event["category_id"], category_id)
        self.assertEqual(event["possible_action"], "REMOVE")
        self.assertEqual(event["before"]["name"], "Categoria CREATE test")
        self.assertIsNone(event["after"])

    def test_office_delete_names_the_real_source_model(self):
        office = OrganizationalStructureOffice.objects.create(
            name="Ufficio test", slug="message-office", organizational_structure=self.structure,
        )
        with self.captureOnCommitCallbacks(execute=True):
            category = self.create_category(organizational_office=office)
        office_id = office.pk
        with self.assertLogs("ticket_events", level="INFO") as logs:
            with self.captureOnCommitCallbacks(execute=True):
                office.delete()
        event = self.event(logs.records)
        self.assertEqual(event["signal"], "post_delete")
        self.assertEqual(event["source_model"], "OrganizationalStructureOffice")
        self.assertEqual(event["category_id"], category.pk)
        self.assertEqual(event["operation"], "UPDATE")
        self.assertEqual(set(event["before"]), set(INDEX_FIELDS))
        self.assertEqual(set(event["after"]), set(INDEX_FIELDS))
        self.assertEqual(event["before"]["organizational_office_id"], office_id)
        self.assertIsNone(event["after"]["organizational_office_id"])
        self.assertEqual(event["after"]["name"], category.name)
        self.assertEqual(event["after"]["organizational_structure_id"], self.structure.pk)
