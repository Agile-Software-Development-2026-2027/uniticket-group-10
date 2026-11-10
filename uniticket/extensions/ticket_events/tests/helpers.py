"""Dati locali dei test e funzione finta che registra operazione e ID."""

from pathlib import Path

from django.conf import settings
from django.db import connection
from unittest.mock import patch
from organizational_area.models import OrganizationalStructure
from uni_ticket.models import TicketCategory

class FakeNotifier:
    """Registra le notifiche ricevute senza contattare servizi esterni."""

    def __init__(self):
        self.events = []

    def __call__(self, operation, category_id):
        self.events.append((operation, category_id))


class CategoryTestsSetup:
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
        # Registra nei test le chiamate a synchronize(), lasciando attivi i signals reali.
        self.synchronize_patch = patch("ticket_events.notifications.synchronize", self.notifier)
        self.synchronize_patch.start()
        self.addCleanup(self.synchronize_patch.stop)

    def create_category(self, **overrides):
        values = {
            "name": "Categoria CREATE test",
            "slug": "create-test",
            "description": "Descrizione di prova",
            "organizational_structure": self.structure,
        }
        values.update(overrides)
        return TicketCategory.objects.create(**values)


    # Esegue il POST originale e le funzioni prenotate con on_commit nei test.
    def post_and_commit(self, url, data=None):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(url, data)
