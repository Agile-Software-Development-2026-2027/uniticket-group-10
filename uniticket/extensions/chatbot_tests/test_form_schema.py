"""Schema dei campi reali, con servizi esterni esclusi dai test."""

import json
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django import forms
from django.contrib.auth import get_user_model
from django.core.validators import MaxLengthValidator, RegexValidator
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from django_form_builder import dynamic_fields as fields
from django_form_builder.forms import BaseDynamicForm
from organizational_area.models import OrganizationalStructure
from uni_ticket.dynamic_form import serialize_form
from uni_ticket.models import Ticket, TicketCategory, TicketCategoryInputList, TicketCategoryModule

from assistant.form_schema import build_form_schema


# Converte un solo campo per mantenere brevi i casi sui diversi tipi.
def schema_field(field):
    form = forms.Form()
    form.fields["campo"] = field
    return build_form_schema(form, category_id=42, module_id=15)["fields"][0]


class FormSchemaTests(SimpleTestCase):
    # Usa davvero il serializer UniTicket e lascia invariati i campi del form ricevuto.
    def test_reuses_uniticket_serializer(self):
        form = forms.Form(initial={"nome": "Valore del form"})
        form.fields["nome"] = forms.CharField(initial="Valore del campo", disabled=True)
        form.fields["captcha"] = fields.CaptchaField()
        with patch("assistant.form_schema.serialize_form", wraps=serialize_form) as original:
            schema = build_form_schema(form, category_id=42, module_id=15)
        original.assert_called_once()
        self.assertEqual(list(original.call_args.args[0].fields), ["nome"])
        self.assertIn("captcha", form.fields)
        self.assertEqual(form.fields["nome"].initial, "Valore del campo")
        result = schema["fields"][0]
        self.assertEqual((result["id"], result["label"], result["initial_value"]),
                         ("nome", "Nome", "Valore del form"))
        self.assertTrue(result["disabled"])
        self.assertNotIn("html", result)
        self.assertNotIn("error_messages", result)

    # Legge valori iniziali e vincoli senza validare i dati eventualmente presenti.
    def test_text_and_initial_values(self):
        form = forms.Form(data={"oggetto": "Risposta utente"}, initial={"oggetto": "Assistenza"})
        form.fields = {
            "oggetto": forms.CharField(label="Oggetto", min_length=1, max_length=100),
            "note": forms.CharField(required=False),
        }
        with patch.object(form, "full_clean") as validate:
            schema = build_form_schema(form, category_id=42, module_id=15)
        validate.assert_not_called()
        self.assertEqual((schema["category_id"], schema["module_id"]), (42, 15))
        subject, notes = schema["fields"]
        self.assertEqual((subject["id"], subject["label"], subject["initial_value"]),
                         ("oggetto", "Oggetto", "Assistenza"))
        self.assertEqual(subject["constraints"]["max_length"], 100)
        self.assertFalse(notes["required"])
        self.assertNotIn("min_length", notes["constraints"])
        self.assertIsNone(notes["initial_value"])
        self.assertEqual(json.loads(json.dumps(schema)), schema)

    # Distingue scelte singole e multiple, senza inventare un limite quando vale zero.
    def test_choices(self):
        single = forms.ChoiceField(choices=[("Sedi", [(8, "Aula"), (9, "Residenza")])], initial=8)
        result = schema_field(single)
        self.assertEqual(result["type"], "choice")
        self.assertEqual(result["constraints"]["choices"][0], {"value": 8, "label": "Aula"})
        self.assertEqual(result["initial_value"], 8)
        for field in [fields.CustomRadioBoxField(), fields.CustomSelectBoxField()]:
            with self.subTest(field=type(field).__name__):
                field.define_value("Aula;Residenza")
                result = schema_field(field)
                self.assertIn({"value": "Aula", "label": "Aula"}, result["constraints"]["choices"])
        for configuration, limit in [("Wi-Fi;Stampante#2", 2), ("Wi-Fi;Stampante", None)]:
            with self.subTest(configuration=configuration):
                field = fields.CustomMultiChoiceField(required=False, initial=["Wi-Fi"])
                field.define_value(configuration)
                result = schema_field(field)
                self.assertEqual(result["type"], "multiple_choice")
                self.assertFalse(result["required"])
                self.assertEqual(result["initial_value"], ["Wi-Fi"])
                self.assertEqual(result["constraints"].get("max_choices"), limit)
                if limit is None:
                    self.assertNotIn("max_choices", result["constraints"])

    # Verifica tipi specifici, limiti numerici, formati data e regole dei validator Django.
    def test_standard_types_and_validators(self):
        cases = [(fields.CustomEmailField(), "email"), (fields.CustomURLField(), "url"),
                 (fields.CustomIPField(), "ip_address"), (fields.PositiveIntegerField(), "integer"),
                 (fields.PositiveFloatField(), "number"), (fields.BaseDateField(), "date"),
                 (fields.BaseDateTimeSimpleField(), "datetime"), (fields.CheckBoxField(), "boolean")]
        for field, expected_type in cases:
            with self.subTest(field=type(field).__name__):
                self.assertEqual(schema_field(field)["type"], expected_type)
        number = schema_field(fields.PositiveFloatField())["constraints"]
        self.assertEqual((number["min_value"], number["decimal_places"]), (0, 3))
        self.assertEqual(schema_field(fields.CheckBoxField())["constraints"]["must_be_true"], True)
        self.assertNotIn("must_be_true", schema_field(fields.CheckBoxField(required=False))["constraints"])
        day = fields.BaseDateField(initial=lambda: date(2026, 1, 2))
        self.assertEqual(schema_field(day)["initial_value"], "2026-01-02")
        self.assertEqual(schema_field(day)["constraints"]["input_formats"], list(day.input_formats))
        decimal = forms.DecimalField(initial=Decimal("1.25"), decimal_places=2, max_digits=4)
        self.assertEqual(schema_field(decimal)["initial_value"], "1.25")
        pattern = RegexValidator(r"^ABC$", inverse_match=True, code="reserved")
        rules = schema_field(forms.CharField(validators=[pattern, MaxLengthValidator(7)]))["constraints"]
        self.assertEqual(rules["max_length"], 7)
        regex_rule = next(rule for rule in rules["validators"] if rule["name"] == "RegexValidator")
        self.assertEqual(regex_rule["pattern"], pattern.regex.pattern)
        self.assertTrue(regex_rule["inverse_match"])
        self.assertNotIn("code", regex_rule)

    # Le regole interne sono descritte e riferite al codice originale, senza eseguirlo.
    def test_custom_rules_and_hidden_initial(self):
        for field in [fields.CustomMACField(), fields.CustomIP4MaskedField(), fields.CustomPasswordField()]:
            with self.subTest(field=type(field).__name__):
                with patch.object(field, "raise_error") as validate:
                    result = schema_field(field)
                validate.assert_not_called()
                self.assertTrue(result["constraints"]["custom_rule"])
        password = fields.CustomPasswordField()
        self.assertEqual(schema_field(password)["constraints"]["pattern"], password.PASSWORD_SEC_REGEX)
        hidden = fields.CustomHiddenField()
        hidden.define_value("Valore configurato")
        self.assertEqual(schema_field(hidden)["initial_value"], "Valore configurato")

    # Mantiene i veri ID dei sotto-campi e descrive le relazioni già applicate dal parent.
    def test_compound_fields(self):
        for field_type in ["DateStartEndComplexField", "BaseDateTimeField", "ProtocolloField"]:
            with self.subTest(field_type=field_type):
                form = BaseDynamicForm(constructor_dict={"Periodo": (field_type, {"required": False}, "")})
                result = build_form_schema(form, category_id=42, module_id=15)["fields"]
                self.assertEqual([field["id"] for field in result], list(form.fields))
                parent = next(iter(form.fields.values())).parent
                if field_type == "DateStartEndComplexField":
                    self.assertEqual(result[0]["constraints"]["less_than_or_equal_to_field"], parent.end.name)
                if field_type == "ProtocolloField":
                    self.assertTrue(all(field["constraints"]["not_empty"] for field in result))
                    self.assertEqual(result[-1]["constraints"]["max_date"], timezone.localdate().isoformat())

    # Legge le colonne dal formset, segnala gli allegati come "file" ed esclude il CAPTCHA.
    def test_table_files_and_excluded_fields(self):
        columns = "Nome#Quantita({'type':'PositiveIntegerField'})#Documento({'type':'CustomFileField'})"
        form = BaseDynamicForm(constructor_dict={"Righe": ("CustomComplexTableField", {"required": True}, columns)})
        form.fields["allegato"] = fields.CustomFileField()
        form.fields["captcha"] = fields.CaptchaField()
        form.fields["captcha_hidden"] = fields.CaptchaHiddenField()
        result = build_form_schema(form, category_id=42, module_id=15)["fields"]
        self.assertEqual([field["id"] for field in result], [next(iter(form.fields)), "allegato"])
        table, attachment = result
        self.assertEqual(attachment["type"], "file")
        self.assertEqual(table["type"], "array")
        self.assertEqual([field["type"] for field in table["fields"]], ["text", "integer", "file"])
        self.assertEqual(table["constraints"]["min_rows"], 1)
        self.assertNotIn("max_rows", table["constraints"])

    # Un campo sconosciuto viene segnalato, anziché fornire uno schema ingannevole.
    def test_unsupported_field(self):
        with self.assertRaisesMessage(NotImplementedError, "campo: Field"):
            schema_field(forms.Field())


class ModuleSchemaTests(TestCase):
    # Costruisce il form da categoria, modulo e campi reali nel solo database temporaneo.
    def test_real_module(self):
        structure = OrganizationalStructure.objects.create(name="Struttura schema", slug="schema", unique_code="SCHEMA")
        category = TicketCategory.objects.create(name="Assistenza Wi-Fi", slug="wifi", description="Supporto aule",
                                                organizational_structure=structure)
        module = TicketCategoryModule.objects.create(name="Modulo", ticket_category=category, is_active=True)
        definitions = [("Email", "CustomEmailField", ""), ("Problemi", "MultiCheckBoxField", "Wi-Fi;Stampante#2")]
        for order, (name, field_type, value) in enumerate(definitions):
            TicketCategoryInputList.objects.create(category_module=module, name=name, field_type=field_type,
                                                  valore=value, is_required=True, ordinamento=order)
        user = get_user_model().objects.create_user(username="schema-user")
        form = module.get_form(show_conditions=True, current_user=user)
        schema = build_form_schema(form, category_id=category.pk, module_id=module.pk)
        self.assertEqual([field["id"] for field in schema["fields"]], list(form.fields))
        self.assertEqual([field["type"] for field in schema["fields"]], ["text", "text", "email", "multiple_choice"])
        self.assertEqual(schema["fields"][0]["initial_value"], category.name)
        self.assertNotIn("max_length", schema["fields"][1]["constraints"])
        self.assertEqual(schema["fields"][-1]["constraints"]["max_choices"], 2)
        self.assertEqual(Ticket.objects.count(), 0)
