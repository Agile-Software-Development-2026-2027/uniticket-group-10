"""Scelta CRUD e collegamento al provider senza richieste HTTP reali."""
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings
from uni_ticket.models import TicketCategory

from ..notifications import notify_index
from ..orchestrator import synchronize
from .helpers import CategoryTestsSetup


class OrchestratorTests(SimpleTestCase):
    # CREATE, UPDATE e DELETE mantengono le azioni già previste.
    def test_each_crud_operation_selects_its_action(self):
        with patch("embedder.embedder.requests.post") as post:
            post.return_value.json.return_value = {"embeddings": [[0.1, 0.2]]}
            for operation, action in (("CREATE", "INDEX"), ("UPDATE", "REINDEX"), ("DELETE", "REMOVE")):
                with self.subTest(operation=operation):
                    category = {"name": "Servizio", "description": "Descrizione"}
                    with patch("ticket_events.orchestrator.snapshot", return_value=category):
                        with self.assertLogs("ticket_events", level="INFO") as logs:
                            synchronize(operation, 42)
                    choices = [line for line in logs.output if "[ORCHESTRATION]" in line]
                    self.assertEqual(len(choices), 1)
                    self.assertIn(f"operation={operation}", choices[0])
                    self.assertIn("category_id=42", choices[0])
                    self.assertIn(f"action={action}", choices[0])

    # La vecchia impostazione non deve più cambiare la chiamata a synchronize().
    @override_settings(TICKET_EVENTS_NOTIFIER=object())
    def test_notification_always_calls_the_imported_orchestrator(self):
        with patch("ticket_events.notifications.synchronize") as orchestrator:
            notify_index("UPDATE", 42)
        orchestrator.assert_called_once_with("UPDATE", 42)

    # DELETE e categorie assenti non preparano testo e non chiamano il modello.
    def test_delete_and_missing_categories_skip_embedding(self):
        for operation in ("CREATE", "UPDATE", "DELETE"):
            with self.subTest(operation=operation):
                with patch("ticket_events.orchestrator.snapshot", return_value=None) as read:
                    with patch("ticket_events.orchestrator.embedding_text") as prepare:
                        with patch("embedder.embedder.requests.post") as post:
                            with self.assertLogs("ticket_events", level="INFO"):
                                synchronize(operation, 42)
                if operation == "DELETE":
                    read.assert_not_called()
                else:
                    read.assert_called_once_with(42, "default")
                prepare.assert_not_called()
                post.assert_not_called()


class ProviderConnectionTests(CategoryTestsSetup, TestCase):
    # Il provider reale riceve il testo salvato nel DB; solo la risposta HTTP è simulata.
    def test_create_and_update_send_saved_text_to_model(self):
        category = self.create_category(name="Assistenza Wi-Fi")
        for operation, description in (("CREATE", "Prima"), ("UPDATE", "Dopo"), ("UPDATE", None)):
            with self.subTest(operation=operation, description=description):
                category.description = description
                category.save(update_fields=["description"])
                category.description = "Solo in memoria, non salvato"
                with patch("embedder.embedder.requests.post") as post:
                    post.return_value.json.return_value = {"embeddings": [[0.1, 0.2, 0.3]]}
                    with self.assertLogs("ticket_events.orchestrator", level="DEBUG") as logs:
                        synchronize(operation, category.pk)
                post.assert_called_once()
                expected = f"Assistenza Wi-Fi\n{description or ''}"
                self.assertEqual(post.call_args.kwargs["json"]["input"], [expected])
                self.assertEqual(logs.records[-1].args, (category.pk, 3))

    # Se il modello fallisce dopo il commit, la categoria rimane salvata.
    def test_model_error_does_not_undo_category_creation(self):
        self.synchronize_patch.stop()
        with patch("embedder.embedder.requests.post", side_effect=RuntimeError("Modello non disponibile")):
            with self.assertLogs("ticket_events", level="ERROR") as logs:
                with self.captureOnCommitCallbacks(execute=True):
                    category = self.create_category()
        self.assertTrue(TicketCategory.objects.filter(pk=category.pk).exists())
        self.assertIn("Modello non disponibile", logs.output[0])
        self.assertIn(str(category.pk), logs.output[0])
