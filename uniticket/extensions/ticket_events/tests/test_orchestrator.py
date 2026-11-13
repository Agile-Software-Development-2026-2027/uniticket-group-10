"""Verifica il flusso CRUD e il provider senza chiamare Ollama."""
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from uni_ticket.models import TicketCategory

from ..interfaces import CategoryOperation
from ..notifications import safe_notify
from ..orchestrator import synchronize
from .helpers import CategoryTestsSetup


class OrchestratorTests(SimpleTestCase):
    # Ogni operazione mantiene l'azione prevista nei log.
    def test_each_crud_operation_selects_its_action(self):
        cases = (
            (CategoryOperation.CREATE, "INDEX"),
            (CategoryOperation.UPDATE, "REINDEX"),
            (CategoryOperation.DELETE, "REMOVE"),
        )
        with patch("ticket_events.orchestrator.snapshot", return_value=None):
            for operation, action in cases:
                with self.subTest(operation=operation):
                    with self.assertLogs("ticket_events", level="INFO") as logs:
                        synchronize(operation, 42)
                    self.assertIn(f"operation={operation}", logs.output[0])
                    self.assertIn(f"action={action}", logs.output[0])

    # safe_notify passa operazione e ID direttamente all'orchestratore.
    def test_notification_calls_orchestrator(self):
        for operation in CategoryOperation:
            with self.subTest(operation=operation):
                with patch("ticket_events.notifications.synchronize") as call:
                    safe_notify(operation, 42)
                call.assert_called_once_with(operation, 42)

    # DELETE e categorie non trovate non devono chiamare Ollama.
    def test_delete_and_missing_categories_skip_model(self):
        for operation in CategoryOperation:
            with self.subTest(operation=operation):
                with patch("ticket_events.orchestrator.snapshot", return_value=None) as read:
                    with patch("embedder.embedder.requests.post") as post:
                        with self.assertLogs("ticket_events", level="INFO"):
                            synchronize(operation, 42)
                if operation == CategoryOperation.DELETE:
                    read.assert_not_called()
                else:
                    read.assert_called_once_with(42, "default")
                post.assert_not_called()


class ProviderConnectionTests(CategoryTestsSetup, TestCase):
    # Il provider reale riceve nome e descrizione salvati; solo HTTP è simulato.
    def test_create_and_update_send_saved_text_to_model(self):
        category = self.create_category(name="Assistenza Wi-Fi")
        cases = (
            (CategoryOperation.CREATE, "Prima"),
            (CategoryOperation.UPDATE, "Dopo"),
            (CategoryOperation.UPDATE, None),
        )
        for operation, description in cases:
            with self.subTest(operation=operation, description=description):
                category.description = description
                category.save(update_fields=["description"])
                category.description = "Modifica non salvata"
                with patch("embedder.embedder.requests.post") as post:
                    post.return_value.json.return_value = {"embeddings": [[0.1, 0.2, 0.3]]}
                    with self.assertLogs("ticket_events.orchestrator", level="INFO") as logs:
                        synchronize(operation, category.pk)
                post.assert_called_once()
                self.assertEqual(post.call_args.kwargs["json"], {
                    "model": "snowflake-arctic-embed2",
                    "input": [f"Assistenza Wi-Fi\n{description or ''}"],
                })
                self.assertIn("dimension=3", logs.output[-1])

    # Un errore HTTP dopo il commit non deve annullare la categoria salvata.
    def test_model_error_preserves_category(self):
        self.synchronize_patch.stop()
        with patch("embedder.embedder.requests.post", side_effect=RuntimeError("Modello non disponibile")):
            with self.assertLogs("ticket_events", level="ERROR") as logs:
                with self.captureOnCommitCallbacks(execute=True):
                    category = self.create_category()
        self.assertTrue(TicketCategory.objects.filter(pk=category.pk).exists())
        self.assertIn("Modello non disponibile", logs.output[0])
