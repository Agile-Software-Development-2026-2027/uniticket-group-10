"""Due verifiche essenziali: scelta CRUD e collegamento dalle notifiche."""
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from ..notifications import safe_notify
from ..orchestrator import synchronize


class OrchestratorTests(SimpleTestCase):
    def test_each_crud_operation_selects_its_action(self):
        for operation, action in (("CREATE", "INDEX"), ("UPDATE", "REINDEX"), ("DELETE", "REMOVE")):
            with self.subTest(operation=operation):
                with self.assertLogs("ticket_events", level="INFO") as logs:
                    synchronize(operation, 42)
                self.assertEqual(len(logs.records), 1)
                self.assertIn(f"operation={operation}", logs.output[0])
                self.assertIn("category_id=42", logs.output[0])
                self.assertIn(f"action={action}", logs.output[0])

    # La vecchia impostazione non deve più cambiare la chiamata a synchronize().
    @override_settings(TICKET_EVENTS_NOTIFIER=object())
    def test_notification_always_calls_the_imported_orchestrator(self):
        for operation in ("CREATE", "UPDATE", "DELETE"):
            with self.subTest(operation=operation):
                with patch("ticket_events.notifications.synchronize") as orchestrator:
                    safe_notify(operation, 42)
                orchestrator.assert_called_once_with(operation, 42)
