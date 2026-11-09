"""Regressione del contratto dei dati e del log DELETE ancora dimostrativo."""

import json

from django.test import TestCase

from .content import embedding_text, snapshot
from .index_fields import INDEX_FIELDS
from .test_create_events import CreateTestsSetup


class IndexContentTests(CreateTestsSetup, TestCase):
    def test_snapshot_contains_exact_index_fields_and_preserves_null(self):
        category = self.create_category(description=None)
        data = snapshot(category.pk, "default")
        self.assertEqual(set(data), set(INDEX_FIELDS))
        self.assertIsNone(data["description"])
        self.assertIsNone(data["organizational_office_id"])

    def test_text_preview_excludes_metadata(self):
        category = self.create_category()
        data = snapshot(category.pk, "default")
        self.assertEqual(
            embedding_text(data),
            "Servizio: Categoria CREATE test\nDescrizione: Descrizione di prova",
        )

    def test_delete_retains_its_demo_log_without_notifying_delete(self):
        with self.captureOnCommitCallbacks(execute=True):
            category = self.create_category()
        category_id = category.pk
        self.notifier.events.clear()
        with self.assertLogs("ticket_events", level="INFO") as logs:
            with self.captureOnCommitCallbacks(execute=True):
                category.delete()
        message = logs.records[0].getMessage()
        event = json.loads(message.removeprefix("[TICKET EVENT] "))
        self.assertEqual(event["operation"], "DELETED")
        self.assertEqual(event["category_id"], category_id)
        self.assertIsNone(event["after"])
        self.assertEqual(self.notifier.events, [])
