"""Due verifiche essenziali: scelta CRUD e collegamento dalle notifiche."""
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from ..notifications import notify_index, safe_notify
from ..orchestrator import synchronize


class OrchestratorTests(SimpleTestCase):
    def test_each_crud_operation_selects_its_action(self):
        for operation, action in (("CREATE", "INDEX"), ("UPDATE", "REINDEX"), ("DELETE", "REMOVE")):
            with self.subTest(operation=operation):
                with self.assertLogs("ticket_events.orchestrator", level="INFO") as logs:
                    synchronize(operation, 42)
                self.assertEqual(len(logs.records), 1)
                self.assertIn(f"operation={operation}", logs.output[0])
                self.assertIn("category_id=42", logs.output[0])
                self.assertIn(f"action={action}", logs.output[0])

    def test_safe_notification_logs_indexer_errors_without_raising(self):
        with patch(
            "ticket_events.notifications.synchronize",
            side_effect=RuntimeError("Indexer unavailable"),
        ):
            with self.assertLogs("ticket_events", level="ERROR") as logs:
                safe_notify("DELETE", 42)

        self.assertIn("operation=DELETE", logs.output[0])
        self.assertIn("category_id=42", logs.output[0])
        self.assertIn("Indexer unavailable", logs.output[0])

    # La vecchia impostazione non deve più cambiare la chiamata a synchronize().
    @override_settings(TICKET_EVENTS_NOTIFIER=object())
    def test_notification_always_calls_the_imported_orchestrator(self):
        with patch("ticket_events.notifications.synchronize", create=True) as orchestrator:
            notify_index("UPDATE", 42)
        orchestrator.assert_called_once_with("UPDATE", 42)
