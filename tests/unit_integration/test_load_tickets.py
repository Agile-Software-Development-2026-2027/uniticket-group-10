import json
from pathlib import Path
import tempfile
import unittest

from prototypes.models import Ticket, load_tickets


class LoadTicketsTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "tickets.json"

    def load(self, records):
        self.path.write_text(json.dumps(records), encoding="utf-8")
        return load_tickets(self.path)

    def test_returns_models_in_input_order_and_preserves_metadata(self):
        tickets = self.load([
            {"ticket": {"id": 2, "title": "Due", "allow_user": True, "footer_text": "Contatti"}},
            {"ticket": {"id": 1, "title": "Uno", "structure": {"name": "Servizi"}, "fields": [{
                "id": 12, "name": "Problema", "field_type": "CustomSelectBoxField",
                "is_required": True, "choices": ["Accesso", "Materiali"],
            }]}},
        ])
        self.assertTrue(all(isinstance(ticket, Ticket) for ticket in tickets))
        self.assertEqual([ticket.id for ticket in tickets], [2, 1])
        self.assertTrue(tickets[0].allow_user)
        self.assertEqual(tickets[1].structure.name, "Servizi")
        self.assertEqual(tickets[1].fields[0].choices, ["Accesso", "Materiali"])

    def test_accepts_plain_ticket_records_and_string_path(self):
        self.load([{"id": 1, "title": "Uno"}])
        self.assertEqual(load_tickets(str(self.path))[0].id, 1)
        self.assertEqual(self.load([]), [])

    def test_rejects_invalid_records_and_duplicate_ids(self):
        for records in ({}, [None], [{"ticket": {"id": True, "title": "Uno"}}],
                        [{"ticket": {"title": "Uno"}}],
                        [{"id": 1, "title": "Uno"}, {"id": 1, "title": "Due"}]):
            with self.subTest(records=records), self.assertRaises(ValueError):
                self.load(records)
