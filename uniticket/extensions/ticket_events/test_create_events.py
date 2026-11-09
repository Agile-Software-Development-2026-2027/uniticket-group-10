"""Verifica CREATE con i modelli originali e un destinatario fittizio."""

import logging
from pathlib import Path

from django.conf import settings
from django.db import connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from organizational_area.models import OrganizationalStructure
from uni_ticket.models import TicketCategory


class FakeNotifier:
    """Registra le notifiche ricevute senza contattare servizi esterni."""

    def __init__(self):
        self.events = []

    def __call__(self, operation, category_id):
        self.events.append((operation, category_id))


class CreateTestsSetup:
    """Prepara dati e connessione esclusivamente nell’ambiente di test isolato."""

    def setUp(self):
        super().setUp()
        self.assertTrue(getattr(settings, "TICKET_EVENTS_ISOLATED_TEST", False))
        self.assertEqual(connection.vendor, "sqlite")
        self.assertIn("memory", str(connection.settings_dict["NAME"]))
        media_root = Path(settings.MEDIA_ROOT).resolve()
        self.assertTrue(media_root.is_relative_to(Path(settings.TICKET_EVENTS_TEST_ROOT).resolve()))
        self.structure = OrganizationalStructure.objects.create(
            name="Struttura CREATE test", slug="create-test", unique_code="CREATE-TEST",
        )
        self.notifier = FakeNotifier()
        # La sostituzione riguarda il confine di notifica, lasciando attivi i signals reali.
        configured_notifier = override_settings(TICKET_EVENTS_NOTIFIER=self.notifier)
        configured_notifier.enable()
        self.addCleanup(configured_notifier.disable)

    def create_category(self, **overrides):
        values = {
            "name": "Categoria CREATE test",
            "slug": "create-test",
            "description": "Descrizione di prova",
            "organizational_structure": self.structure,
        }
        values.update(overrides)
        return TicketCategory.objects.create(**values)


class CreateNotificationTests(CreateTestsSetup, TestCase):
    def test_creation_notifies_once_with_correct_id(self):
        with self.captureOnCommitCallbacks(execute=True):
            category = self.create_category()
        self.assertEqual(self.notifier.events, [("CREATE", category.pk)])

    def test_inactive_category_is_also_notified(self):
        with self.captureOnCommitCallbacks(execute=True):
            category = self.create_category(is_active=False)
        self.assertFalse(category.is_active)
        self.assertEqual(self.notifier.events, [("CREATE", category.pk)])

    def test_notification_waits_for_commit_callback(self):
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            category = self.create_category()
            self.assertEqual(self.notifier.events, [])
        self.assertEqual(len(callbacks), 1)
        callbacks[0]()
        self.assertEqual(self.notifier.events, [("CREATE", category.pk)])

    def test_callback_keeps_id_when_instance_changes(self):
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            category = self.create_category()
        original_id = category.pk
        # Una callback differita deve conservare il valore dell’ID al salvataggio.
        category.pk = None
        callbacks[0]()
        self.assertEqual(self.notifier.events, [("CREATE", original_id)])

    def test_fixture_creation_is_skipped(self):
        category = TicketCategory(
            name="Categoria fixture", slug="fixture", organizational_structure=self.structure,
            # Le fixture forniscono anche i timestamp, senza eseguire gli auto_now.
            created=timezone.now(), modified=timezone.now(),
        )
        with self.captureOnCommitCallbacks(execute=True):
            category.save_base(raw=True)
        self.assertEqual(self.notifier.events, [])

    def test_notifier_error_is_logged_without_losing_category(self):
        def failing_notifier(operation, category_id):
            raise RuntimeError("Destinatario indisponibile")

        with override_settings(TICKET_EVENTS_NOTIFIER=failing_notifier):
            with self.assertLogs("ticket_events", level=logging.ERROR) as logs:
                with self.captureOnCommitCallbacks(execute=True):
                    category = self.create_category()
        self.assertTrue(TicketCategory.objects.filter(pk=category.pk).exists())
        self.assertIn("CREATE", logs.output[0])
        self.assertIn(str(category.pk), logs.output[0])
        self.assertIn("Destinatario indisponibile", logs.output[0])
        self.assertIsNotNone(logs.records[0].exc_info)

    def test_dotted_path_notifier_is_supported(self):
        with override_settings(TICKET_EVENTS_NOTIFIER="ticket_events.notifications.log_notification"):
            with self.assertLogs("ticket_events", level=logging.INFO) as logs:
                with self.captureOnCommitCallbacks(execute=True):
                    category = self.create_category()
        self.assertTrue(any('"operation": "CREATE"' in entry for entry in logs.output))
        self.assertTrue(any(f'"category_id": {category.pk}' in entry for entry in logs.output))

    def test_invalid_notifier_is_logged(self):
        with override_settings(TICKET_EVENTS_NOTIFIER=42):
            with self.assertLogs("ticket_events", level=logging.ERROR):
                with self.captureOnCommitCallbacks(execute=True):
                    category = self.create_category()
        self.assertTrue(TicketCategory.objects.filter(pk=category.pk).exists())

    def test_demo_post_returns_created_even_when_notifier_fails(self):
        def failing_notifier(operation, category_id):
            raise RuntimeError("Errore simulato")

        # Il prototipo resta un punto d’ingresso locale per provare il CRUD reale.
        with override_settings(
            RECEIVER_DEMO=True,
            ROOT_URLCONF="ticket_events.demo_urls",
            TICKET_EVENTS_NOTIFIER=failing_notifier,
        ):
            with self.assertLogs("ticket_events", level=logging.ERROR):
                with self.captureOnCommitCallbacks(execute=True):
                    response = self.client.post(
                        "/api/categories/",
                        data={"name": "CREATE tramite API", "description": "Prova"},
                        content_type="application/json",
                    )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(TicketCategory.objects.filter(pk=response.json()["id"]).exists())


class CreateTransactionTests(CreateTestsSetup, TransactionTestCase):
    def test_real_commit_delivers_notification(self):
        with transaction.atomic():
            category = self.create_category()
            self.assertEqual(self.notifier.events, [])
        self.assertEqual(self.notifier.events, [("CREATE", category.pk)])

    def test_rollback_discards_notification_and_category(self):
        with self.assertRaises(ValueError):
            with transaction.atomic():
                category = self.create_category()
                raise ValueError("Annullamento di prova")
        self.assertEqual(self.notifier.events, [])
        self.assertFalse(TicketCategory.objects.filter(pk=category.pk).exists())

    def test_autocommit_notifies_immediately(self):
        category = self.create_category()
        self.assertEqual(self.notifier.events, [("CREATE", category.pk)])

    def test_failed_nested_transaction_does_not_notify(self):
        with transaction.atomic():
            with self.assertRaises(ValueError):
                with transaction.atomic():
                    self.create_category()
                    raise ValueError("Rollback del savepoint")
        self.assertEqual(self.notifier.events, [])
