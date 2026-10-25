import json
from pathlib import Path
import tempfile
import unittest

from dumps.extract_tickets import extract_field, extract_tickets
from prototypes.models import FormField


class ComplexFieldsTests(unittest.TestCase):
    def test_select_box_structure_choices(self):
        raw = "DINCI;DIAM;DIMES;DIMEG;Altra struttura di Ateneo;Ditta esterna per accesso temporaneo"
        field = extract_field(1194, {"name": "Struttura di appartenenza",
                                   "field_type": "CustomSelectBoxField", "is_required": True,
                                   "valore": raw})
        self.assertEqual(field["choices"], ["DINCI", "DIAM", "DIMES", "DIMEG",
                                           "Altra struttura di Ateneo", "Ditta esterna per accesso temporaneo"])
        self.assertEqual(FormField.model_validate(field).choices, field["choices"])
        self.assertEqual(field["valore"], raw)

    def test_checkbox_choices_preserve_original_value_without_mutating_source(self):
        original = {"name": "Problema", "field_type": "MultiCheckBoxField", "is_required": True,
                    "valore": " Accesso ; Materiali del corso; ; Altro ", "aiuto": "Scegli"}
        field = extract_field(12, original)
        self.assertEqual(field["choices"], ["Accesso", "Materiali del corso", "Altro"])
        self.assertEqual(field["valore"], original["valore"])
        self.assertEqual(original["valore"], " Accesso ; Materiali del corso; ; Altro ")
        self.assertNotIn("choices", original)
        self.assertEqual(FormField.model_validate(field).choices, field["choices"])

    def test_table_columns_with_choices_quotes_and_hashes(self):
        raw = ("corso({'type': 'CustomSelectBoxField', 'required': True, "
               "'label': \"Corso dell'ateneo #1 (scelta)\", 'choices': ' A; B '})#"
               "ore({'type': 'PositiveIntegerField', 'required': False, 'label': 'Ore'})")
        field = extract_field(198, {"name": "Insegnamenti", "field_type": "CustomComplexTableField",
                                    "is_required": True, "valore": raw})
        self.assertEqual(field["valore"], raw)
        columns = FormField.model_validate(field).columns
        self.assertEqual([column.name for column in columns], ["corso", "ore"])
        self.assertEqual(columns[0].choices, ["A", "B"])
        self.assertEqual(columns[0].label, "Corso dell'ateneo #1 (scelta)")
        self.assertFalse(columns[1].required)

    def test_invalid_tables_are_rejected_without_executing_expressions(self):
        for raw in ("broken", "campo(__import__('os').getcwd())",
                    "campo({'type': 'CustomCharField'})",
                    "a({'type':'X','required':True,'label':'A'})#a({'type':'X','required':False,'label':'B'})"):
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, "Campo 99"):
                extract_field(99, {"field_type": "CustomComplexTableField", "valore": raw})

    def test_extraction_attaches_parsed_fields_to_ticket(self):
        records = [
            {"model": "uni_ticket.ticketcategory", "pk": 1, "fields": {"name": "Servizio"}},
            {"model": "uni_ticket.ticketcategorymodule", "pk": 2, "fields": {"ticket_category": 1}},
            {"model": "uni_ticket.ticketcategoryinputlist", "pk": 3, "fields": {
                "name": "Problema", "field_type": "MultiCheckBoxField", "is_required": False,
                "category_module": 2, "valore": "Accesso;Materiali"}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dump.json"
            path.write_text(json.dumps(records))
            field = extract_tickets(path)[0]["ticket"]["fields"][0]
        self.assertEqual(field["id"], 3)
        self.assertEqual(field["choices"], ["Accesso", "Materiali"])
        self.assertEqual(field["valore"], "Accesso;Materiali")
