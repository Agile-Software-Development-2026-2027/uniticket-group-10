"""Preparazione condivisa dei test CRUD e destinatario fittizio."""

from pathlib import Path

from django.conf import settings
from django.db import connection
from django.test import override_settings
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


