import json
import unittest

from dumps.extract_tickets import extract_field
from prototypes.models import FormField, OrganizationalStructure, Ticket


class LLMContextTests(unittest.TestCase):
    def test_ticket_fields_follow_ordinamento_without_mutating_original_order(self):
        fields = [
            FormField(id=1, name="Ultimo", field_type="CustomCharField", is_required=False, ordinamento=3),
            FormField(id=2, name="Primo", field_type="CustomCharField", is_required=False, ordinamento=0),
            FormField(id=3, name="Secondo", field_type="CustomCharField", is_required=False, ordinamento=1),
            FormField(id=4, name="Terzo", field_type="CustomCharField", is_required=False, ordinamento=1),
        ]
        ticket = Ticket(id=146, title="Assistenza", fields=fields)
        context = ticket.as_llm_context()
        self.assertEqual([field["name"] for field in context["fields"]],
                         ["Primo", "Secondo", "Terzo", "Ultimo"])
        self.assertEqual([field.id for field in ticket.fields], [1, 2, 3, 4])

    def test_structure_context_includes_description_when_present(self):
        structure = OrganizationalStructure(id=5, name=" Servizi informatici ", description="Interna")
        self.assertEqual(structure.as_llm_context(), {"name": "Servizi informatici", "description": "Interna"})
        self.assertEqual(OrganizationalStructure(name="  ").as_llm_context(), {})
        self.assertEqual(OrganizationalStructure(name="Servizi", description=None).as_llm_context(),
                         {"name": "Servizi"})
        self.assertEqual(OrganizationalStructure(description="Informazioni").as_llm_context(),
                         {"description": "Informazioni"})

    def test_ticket_context_selects_metadata_and_uses_field_context(self):
        field = self.field(aiuto="Indica il problema")
        ticket = Ticket(id=146, title="Assistenza", description="Supporto piattaforma",
                        structure={"id": 5, "name": "Servizi informatici", "description": "Interna"},
                        fields=[field], header_text="Introduzione", footer_text="Contatti", is_active=True)
        original = ticket.model_dump()
        context = ticket.as_llm_context()
        self.assertEqual(context, {
            "title": "Assistenza", "description": "Supporto piattaforma",
            "structure": {"name": "Servizi informatici", "description": "Interna"},
            "fields": [field.as_llm_context()], "header_text": "Introduzione", "footer_text": "Contatti",
        })
        json.dumps(context)
        self.assertEqual(ticket.model_dump(), original)

    def test_ticket_context_omits_absent_and_blank_parts(self):
        ticket = Ticket(id=146, title="Assistenza", description=None, header_text="  ", footer_text=None)
        self.assertEqual(ticket.as_llm_context(), {"title": "Assistenza"})

    def field(self, **changes):
        return FormField(id=1, name="Problema", field_type="CustomCharField",
                         is_required=False, **changes)

    def test_omits_empty_values_and_internal_metadata(self):
        context = self.field(aiuto="  ", pre_text=None).as_llm_context()
        self.assertEqual(context, {"name": "Problema", "field_type": "CustomCharField", "required": False})
        json.dumps(context)

    def test_renames_metadata_and_preserves_zero_and_false(self):
        for value in (0, False):
            with self.subTest(value=value):
                context = self.field(valore=value, aiuto="Indica il problema", pre_text="Dettagli").as_llm_context()
                self.assertIs(context["default_value"], value)
                self.assertEqual(context["help_message"], "Indica il problema")
                self.assertEqual(context["pre_text"], "Dettagli")

    def test_selection_value_is_choices_not_default(self):
        for field_type in ("MultiCheckBoxField", "CustomSelectBoxField", "CustomRadioBoxField"):
            with self.subTest(field_type=field_type):
                field = FormField.model_validate(extract_field(1, {
                    "name": "Struttura", "field_type": field_type, "is_required": True, "valore": "DINCI;DIAM",
                }))
                context = field.as_llm_context()
                self.assertEqual(context["choices"], ["DINCI", "DIAM"])
                self.assertNotIn("default_value", context)
                self.assertNotIn("valore", context)
                self.assertEqual(field.valore, "DINCI;DIAM")
                self.assertEqual(field.model_dump()["valore"], "DINCI;DIAM")

    def test_table_columns_keep_labels_and_omit_empty_choices(self):
        field = FormField.model_validate(extract_field(1, {
            "name": "Insegnamenti", "field_type": "CustomComplexTableField", "is_required": True,
            "valore": "ore({'type':'PositiveIntegerField','label':'Ore di lezione','required':False})",
        }))
        context = field.as_llm_context()
        self.assertEqual(context["columns"], [{"name": "ore", "label": "Ore di lezione",
                                               "field_type": "PositiveIntegerField", "required": False}])
        self.assertNotIn("default_value", context)
        self.assertNotIn("choices", context)
        self.assertEqual(field.valore,
                         "ore({'type':'PositiveIntegerField','label':'Ore di lezione','required':False})")

    def test_empty_nested_default_values_are_pruned(self):
        context = self.field(valore={"empty": [], "zero": 0, "nested": {"blank": " "}}).as_llm_context()
        self.assertEqual(context["default_value"], {"zero": 0})
