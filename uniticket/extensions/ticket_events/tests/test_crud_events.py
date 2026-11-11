"""Stesse regole di ricezione per CREATE, UPDATE e DELETE."""
from contextlib import nullcontext
from unittest.mock import patch

from django.db import transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from uni_ticket.models import TicketCategory, TicketCategoryModule

from .helpers import CategoryTestsSetup

OPERATIONS = ("CREATE", "UPDATE", "DELETE")


class CrudExamples(CategoryTestsSetup):
    # Prepara un contatore per assegnare nomi e slug distinti ai casi.
    def setUp(self):
        super().setUp()
        self.example_number = 0

    # Restituisce una categoria nuova per CREATE e già salvata per UPDATE/DELETE.
    def prepare_category(self, operation, active=False):
        self.example_number += 1
        category = TicketCategory(
            name=f"Categoria {self.example_number}", slug=f"categoria-{self.example_number}",
            description="Prima", organizational_structure=self.structure, is_active=active,
        )
        if operation != "CREATE":
            if isinstance(self, TestCase):
                with self.captureOnCommitCallbacks(execute=True):
                    category.save()
            else:
                category.save()
        self.notifier.events.clear()
        return category

    # Esegue l’operazione richiesta e restituisce l’ID, anche dopo DELETE.
    def change_category(self, operation, category):
        category_id = category.pk
        if operation == "DELETE":
            category.delete()
            return category_id
        if operation == "UPDATE":
            category.description = "Dopo"
        category.save()
        return category.pk

    # Controlla che il database conservi il risultato dell’operazione.
    def assert_saved(self, operation, category_id):
        self.assertEqual(TicketCategory.objects.filter(pk=category_id).exists(), operation != "DELETE")
        if operation == "UPDATE":
            self.assertEqual(TicketCategory.objects.get(pk=category_id).description, "Dopo")


class CrudSignalTests(CrudExamples, TestCase):
    # Ogni operazione aspetta il commit e conserva l’ID originale, anche su categorie inattive.
    def test_notification_waits_and_keeps_id(self):
        for operation in OPERATIONS:
            for active in (False, True):
                with self.subTest(operation=operation, active=active):
                    category = self.prepare_category(operation, active)
                    with self.captureOnCommitCallbacks(execute=False) as callbacks:
                        category_id = self.change_category(operation, category)
                        self.assertEqual(self.notifier.events, [])
                    self.assertEqual(len(callbacks), 1)
                    self.assertEqual(category.is_active, active)
                    if operation == "DELETE":
                        self.assertIsNone(category.pk)
                    category.pk = None
                    callbacks[0]()
                    self.assertEqual(self.notifier.events, [(operation, category_id)])

    def test_delete_signal_only_logs_action_after_commit(self):
        with self.captureOnCommitCallbacks(execute=True):
            category = self.create_category()
        category_id = category.pk

        self.synchronize_patch.stop()
        with patch("ticket_events.repository.QdrantIndexRepository.delete") as delete:
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                category.delete()
                delete.assert_not_called()

            self.assertEqual(len(callbacks), 1)
            with self.assertLogs("ticket_events.orchestrator", level="INFO") as logs:
                callbacks[0]()

        delete.assert_not_called()
        self.assertIn("operation=DELETE", logs.output[0])
        self.assertIn(f"category_id={category_id}", logs.output[0])
        self.assertIn("action=REMOVE", logs.output[0])

    # I caricamenti raw non notificano né creazioni né aggiornamenti.
    def test_fixture_saves_do_not_notify(self):
        for operation in ("CREATE", "UPDATE"):
            with self.subTest(operation=operation):
                category = self.prepare_category(operation)
                category.created = category.modified = timezone.now()
                category.description = "Fixture"
                with self.captureOnCommitCallbacks(execute=True):
                    category.save_base(raw=True)
                self.assertEqual(self.notifier.events, [])

    # Un errore nell’orchestratore viene registrato e non annulla il CRUD.
    def test_orchestrator_error_preserves_crud(self):
        for operation in OPERATIONS:
            with self.subTest(operation=operation):
                category = self.prepare_category(operation)
                with patch("ticket_events.notifications.synchronize", side_effect=RuntimeError("Errore di prova")):
                    with self.assertLogs("ticket_events", level="ERROR") as logs:
                        with self.captureOnCommitCallbacks(execute=True):
                            category_id = self.change_category(operation, category)
                self.assert_saved(operation, category_id)
                self.assertIn(operation, logs.output[0])
                self.assertIn(str(category_id), logs.output[0])
                self.assertIn("Errore di prova", logs.output[0])
                self.assertIsNotNone(logs.records[0].exc_info)

    # QuerySet.delete notifica ogni categoria; ripetere la cancellazione non crea eventi.
    def test_queryset_delete_and_absent_categories(self):
        categories = [self.prepare_category("DELETE") for _ in range(2)]
        ids = {category.pk for category in categories}
        with self.captureOnCommitCallbacks(execute=True):
            TicketCategory.objects.filter(pk__in=ids).delete()
        self.assertCountEqual(self.notifier.events, [("DELETE", pk) for pk in ids])
        self.notifier.events.clear()
        with self.captureOnCommitCallbacks(execute=True):
            TicketCategory.objects.filter(pk__in=ids).delete()
        self.assertEqual(self.notifier.events, [])

    # I moduli eliminati insieme alla categoria non duplicano la notifica DELETE.
    def test_cascading_modules_do_not_duplicate_delete(self):
        category = self.prepare_category("DELETE")
        category_id = category.pk
        module = TicketCategoryModule.objects.create(name="Modulo", ticket_category=category)
        with self.captureOnCommitCallbacks(execute=True):
            category.delete()
        self.assertFalse(TicketCategoryModule.objects.filter(pk=module.pk).exists())
        self.assertEqual(self.notifier.events, [("DELETE", category_id)])


class CrudTransactionTests(CrudExamples, TransactionTestCase):
    # Con una transazione esplicita la notifica arriva soltanto all’uscita da atomic.
    def test_commit_delivers_each_operation(self):
        for operation in OPERATIONS:
            with self.subTest(operation=operation):
                category = self.prepare_category(operation)
                with transaction.atomic():
                    category_id = self.change_category(operation, category)
                    self.assertEqual(self.notifier.events, [])
                self.assertEqual(self.notifier.events, [(operation, category_id)])
                self.assert_saved(operation, category_id)

    # Senza atomic la notifica arriva al termine del save o delete.
    def test_autocommit_delivers_each_operation(self):
        for operation in OPERATIONS:
            with self.subTest(operation=operation):
                category = self.prepare_category(operation)
                category_id = self.change_category(operation, category)
                self.assertEqual(self.notifier.events, [(operation, category_id)])

    # Rollback completo e rollback di un savepoint scartano tutte le notifiche.
    def test_rollback_discards_each_operation(self):
        for operation in OPERATIONS:
            for nested in (False, True):
                with self.subTest(operation=operation, nested=nested):
                    category = self.prepare_category(operation)
                    outer = transaction.atomic() if nested else nullcontext()
                    with outer:
                        with self.assertRaises(ValueError):
                            with transaction.atomic():
                                category_id = self.change_category(operation, category)
                                raise ValueError("Rollback di prova")
                    self.assertEqual(self.notifier.events, [])
                    self.assertEqual(TicketCategory.objects.filter(pk=category_id).exists(), operation != "CREATE")
                    if operation == "UPDATE":
                        self.assertEqual(TicketCategory.objects.get(pk=category_id).description, "Prima")
