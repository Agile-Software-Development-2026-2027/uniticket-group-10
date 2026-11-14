"""Verifica il flusso CRUD e il provider senza chiamare Ollama."""
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from qdrant_client import QdrantClient
from uni_ticket.models import TicketCategory

from database.repository import QdrantIndexRepository
from ..interfaces import CategoryOperation
from ..notifications import safe_notify
from ..orchestrator import synchronize
from .helpers import CategoryTestsSetup


class OrchestratorTests(SimpleTestCase):
    def test_create_update_delete_round_trip_through_orchestrator_and_qdrant(self):
        client = QdrantClient(":memory:")
        self.addCleanup(client.close)
        repository = QdrantIndexRepository(
            collection_name="orchestrator_crud_test",
            client=client,
        )
        category = {
            "name": "Assistenza Wi-Fi",
            "description": "Prima descrizione",
            "organizational_structure_id": 7,
            "organizational_office_id": None,
            "allow_user": True,
            "allow_employee": False,
            "allow_anonymous": False,
            "allow_guest": True,
            "allow_spid_cie": False,
            "is_active": True,
        }
        updated_category = {
            **category,
            "description": "Descrizione aggiornata",
            "is_active": False,
        }

        with patch("ticket_events.orchestrator.index_repository", repository):
            with patch(
                "ticket_events.orchestrator.snapshot",
                side_effect=[category, updated_category],
            ) as read:
                with patch("ticket_events.orchestrator.provider") as embedder:
                    embedder.embed.side_effect = [[1.0, 0.0], [0.0, 1.0]]
                    with self.assertLogs("ticket_events.orchestrator", level="INFO"):
                        synchronize(CategoryOperation.CREATE, 42)

                    created = client.retrieve(
                        "orchestrator_crud_test",
                        ids=[42],
                        with_payload=True,
                        with_vectors=True,
                    )
                    self.assertEqual(len(created), 1)
                    self.assertEqual(created[0].vector, [1.0, 0.0])
                    self.assertTrue(created[0].payload["is_active"])

                    with self.assertLogs("ticket_events.orchestrator", level="INFO"):
                        synchronize(CategoryOperation.UPDATE, 42)

                    updated = client.scroll(
                        "orchestrator_crud_test",
                        with_payload=True,
                        with_vectors=True,
                    )[0]
                    self.assertEqual(len(updated), 1)
                    self.assertEqual(updated[0].id, 42)
                    self.assertEqual(updated[0].vector, [0.0, 1.0])
                    self.assertFalse(updated[0].payload["is_active"])

                    with self.assertLogs("ticket_events.orchestrator", level="INFO"):
                        synchronize(CategoryOperation.DELETE, 42)

        self.assertEqual(read.call_count, 2)
        self.assertEqual(client.retrieve("orchestrator_crud_test", ids=[42]), [])

    # Ogni operazione mantiene l'azione prevista nei log.
    def test_each_crud_operation_selects_its_action(self):
        cases = (
            (CategoryOperation.CREATE, "INDEX"),
            (CategoryOperation.UPDATE, "REINDEX"),
            (CategoryOperation.DELETE, "REMOVE"),
        )
        with patch("ticket_events.orchestrator.snapshot", return_value=None):
            with patch("ticket_events.orchestrator.index_repository") as repository:
                for operation, action in cases:
                    with self.subTest(operation=operation):
                        with self.assertLogs("ticket_events", level="INFO") as logs:
                            synchronize(operation, 42)
                        self.assertTrue(any(
                            f"operation={operation}" in message
                            and f"action={action}" in message
                            for message in logs.output
                        ))
                self.assertEqual(repository.delete.call_count, 3)

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
                    with patch("ticket_events.orchestrator.index_repository") as repository:
                        with patch("embedder.embedder.requests.post") as post:
                            with self.assertLogs("ticket_events", level="INFO"):
                                synchronize(operation, 42)
                repository.delete.assert_called_once_with(42)
                repository.upsert.assert_not_called()
                post.assert_not_called()
                if operation == CategoryOperation.DELETE:
                    read.assert_not_called()
                else:
                    read.assert_called_once_with(42, "default")


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
                with patch("ticket_events.orchestrator.index_repository") as repository:
                    with patch("embedder.embedder.requests.post") as post:
                        post.return_value.json.return_value = {"embeddings": [[0.1, 0.2, 0.3]]}
                        with self.assertLogs("ticket_events.orchestrator", level="INFO") as logs:
                            synchronize(operation, category.pk)
                post.assert_called_once()
                self.assertEqual(post.call_args.kwargs["json"], {
                    "model": "snowflake-arctic-embed2",
                    "input": [f"Assistenza Wi-Fi\n{description or ''}"],
                })
                self.assertTrue(any("dimension=3" in message for message in logs.output))
                repository.upsert.assert_called_once_with(
                    category.pk,
                    [0.1, 0.2, 0.3],
                    {
                        "organizational_structure_id": category.organizational_structure_id,
                        "organizational_office_id": category.organizational_office_id,
                        "allow_user": category.allow_user,
                        "allow_employee": category.allow_employee,
                        "allow_anonymous": category.allow_anonymous,
                        "allow_guest": category.allow_guest,
                        "allow_spid_cie": category.allow_spid_cie,
                        "is_active": category.is_active,
                    },
                )

    # Un errore HTTP dopo il commit non deve annullare la categoria salvata.
    def test_model_error_preserves_category(self):
        self.synchronize_patch.stop()
        with patch("embedder.embedder.requests.post", side_effect=RuntimeError("Modello non disponibile")):
            with self.assertLogs("ticket_events", level="ERROR") as logs:
                with self.captureOnCommitCallbacks(execute=True):
                    category = self.create_category()
        self.assertTrue(TicketCategory.objects.filter(pk=category.pk).exists())
        self.assertIn("Modello non disponibile", logs.output[0])
