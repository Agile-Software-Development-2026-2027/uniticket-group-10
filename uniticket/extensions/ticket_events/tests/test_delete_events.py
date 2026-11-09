"""TDD di DELETE con modelli originali, notifier fittizio e database isolato."""

import json
import logging

from django.db import transaction
from django.test import TestCase, TransactionTestCase, override_settings
from uni_ticket.models import TicketCategory, TicketCategoryModule

from .helpers import CategoryTestsSetup


class DeleteTestsSetup(CategoryTestsSetup):
    def setUp(self):
        super().setUp()
        if isinstance(self, TestCase):
            with self.captureOnCommitCallbacks(execute=True):
                self.category = self.create_category()
        else:
            self.category = self.create_category()
        self.notifier.events.clear()


class DeleteNotificationTests(DeleteTestsSetup, TestCase):
    def test_delete_notifies_once_with_original_id(self):
        category_id = self.category.pk
        with self.captureOnCommitCallbacks(execute=True):
            self.category.delete()
        self.assertIsNone(self.category.pk)
        self.assertEqual(self.notifier.events, [("DELETE", category_id)])

    def test_waits_for_commit_and_keeps_deleted_id(self):
        category_id = self.category.pk
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            self.category.delete()
            self.assertEqual(self.notifier.events, [])
        self.assertEqual(len(callbacks), 1)
        self.assertIsNone(self.category.pk)
        callbacks[0]()
        self.assertEqual(self.notifier.events, [("DELETE", category_id)])

    def test_inactive_category_is_notified_on_delete(self):
        self.assertFalse(self.category.is_active)
        category_id = self.category.pk
        with self.captureOnCommitCallbacks(execute=True):
            self.category.delete()
        self.assertEqual(self.notifier.events, [("DELETE", category_id)])

    def test_queryset_delete_notifies_each_category(self):
        with self.captureOnCommitCallbacks(execute=True):
            other = self.create_category(slug="other-delete")
        ids = {self.category.pk, other.pk}
        self.notifier.events.clear()
        with self.captureOnCommitCallbacks(execute=True):
            TicketCategory.objects.filter(pk__in=ids).delete()
        self.assertCountEqual(self.notifier.events, [("DELETE", pk) for pk in ids])

    def test_delete_of_absent_category_does_not_notify_again(self):
        category_id = self.category.pk
        with self.captureOnCommitCallbacks(execute=True):
            self.category.delete()
        self.notifier.events.clear()
        with self.captureOnCommitCallbacks(execute=True):
            TicketCategory.objects.filter(pk=category_id).delete()
        self.assertEqual(self.notifier.events, [])

    def test_cascading_modules_do_not_duplicate_category_notification(self):
        module = TicketCategoryModule.objects.create(
            name="Modulo fittizio", ticket_category=self.category,
        )
        category_id = self.category.pk
        with self.captureOnCommitCallbacks(execute=True):
            self.category.delete()
        self.assertFalse(TicketCategoryModule.objects.filter(pk=module.pk).exists())
        self.assertEqual(self.notifier.events, [("DELETE", category_id)])

    def test_notifier_failure_preserves_deletion_and_logs_traceback(self):
        def failing_notifier(operation, category_id):
            raise RuntimeError("Errore DELETE simulato")

        category_id = self.category.pk
        with override_settings(TICKET_EVENTS_NOTIFIER=failing_notifier):
            with self.assertLogs("ticket_events", level=logging.ERROR) as logs:
                with self.captureOnCommitCallbacks(execute=True):
                    self.category.delete()
        self.assertFalse(TicketCategory.objects.filter(pk=category_id).exists())
        self.assertIn("DELETE", logs.output[0])
        self.assertIn(str(category_id), logs.output[0])
        self.assertIsNotNone(logs.records[0].exc_info)

    def test_default_demo_notifier_logs_delete(self):
        category_id = self.category.pk
        with override_settings(TICKET_EVENTS_NOTIFIER="ticket_events.notifications.log_notification"):
            with self.assertLogs("ticket_events", level=logging.INFO) as logs:
                with self.captureOnCommitCallbacks(execute=True):
                    self.category.delete()
        message = logs.records[0].getMessage().removeprefix("[TICKET EVENT] ")
        event = json.loads(message)
        self.assertEqual(event["signal"], "post_delete")
        self.assertEqual(event["source_model"], "TicketCategory")
        self.assertEqual(event["operation"], "DELETE")
        self.assertEqual(event["category_id"], category_id)
        self.assertEqual(event["possible_action"], "REMOVE")
        self.assertIsNone(event["after"])


class DeleteTransactionTests(DeleteTestsSetup, TransactionTestCase):
    def test_real_commit_delivers_delete(self):
        category_id = self.category.pk
        with transaction.atomic():
            self.category.delete()
            self.assertEqual(self.notifier.events, [])
        self.assertEqual(self.notifier.events, [("DELETE", category_id)])

    def test_rollback_restores_category_and_discards_notification(self):
        category_id = self.category.pk
        with self.assertRaises(ValueError):
            with transaction.atomic():
                self.category.delete()
                raise ValueError("Rollback DELETE")
        self.assertTrue(TicketCategory.objects.filter(pk=category_id).exists())
        self.assertEqual(self.notifier.events, [])

    def test_delete_in_autocommit_notifies_after_internal_transaction(self):
        category_id = self.category.pk
        self.category.delete()
        self.assertEqual(self.notifier.events, [("DELETE", category_id)])

    def test_savepoint_rollback_discards_delete(self):
        category_id = self.category.pk
        with transaction.atomic():
            with self.assertRaises(ValueError):
                with transaction.atomic():
                    self.category.delete()
                    raise ValueError("Rollback savepoint DELETE")
        self.assertTrue(TicketCategory.objects.filter(pk=category_id).exists())
        self.assertEqual(self.notifier.events, [])
