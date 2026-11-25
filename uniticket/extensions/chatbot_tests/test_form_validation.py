"""Validazione dei dati: errori divisi tra campi mancanti e valori non validi."""

from django import forms
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from django_form_builder import dynamic_fields as fields

from assistant.form_validation import validate_form


# Un form semplice con i tipi di campo più comuni
class SampleForm(forms.Form):
    nome = forms.CharField(max_length=5)
    email = forms.EmailField()
    sede = forms.ChoiceField(choices=[("aula", "Aula"), ("residenza", "Residenza")])
    note = forms.CharField(required=False)


VALID_DATA = {"nome": "Mario", "email": "mario@unical.it", "sede": "aula"}


class ValidateFormTests(SimpleTestCase):
    # Dati corretti: nessun errore e form valido
    def test_valid_data(self):
        result = validate_form(SampleForm(data=VALID_DATA))
        self.assertEqual(result, {"valid": True, "missing_fields": [], "errors": []})

    # I campi obbligatori vuoti finiscono in missing_fields, quelli facoltativi no
    def test_missing_required_fields(self):
        result = validate_form(SampleForm(data={"nome": "Mario"}))
        self.assertFalse(result["valid"])
        self.assertEqual(sorted(result["missing_fields"]), ["email", "sede"])
        self.assertNotIn("note", result["missing_fields"])
        self.assertEqual(result["errors"], [])

    # I valori sbagliati finiscono in errors con il codice di Django
    def test_invalid_values(self):
        data = {"nome": "Giovanni", "email": "mario@", "sede": "mensa"}
        result = validate_form(SampleForm(data=data))
        self.assertFalse(result["valid"])
        self.assertEqual(result["missing_fields"], [])
        codes = {error["field"]: error["code"] for error in result["errors"]}
        self.assertEqual(codes, {"nome": "max_length", "email": "invalid", "sede": "invalid_choice"})
        for error in result["errors"]:
            self.assertTrue(error["message"])

    # Gli errori del form intero hanno field None, quelli senza codice diventano "invalid"
    def test_non_field_error_without_code(self):
        class DatesForm(SampleForm):
            def clean(self):
                raise ValidationError("La data di inizio deve precedere quella di fine.")

        result = validate_form(DatesForm(data=VALID_DATA))
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"], [{
            "field": None,
            "code": "invalid",
            "message": "La data di inizio deve precedere quella di fine.",
        }])

    # Il CAPTCHA non è nello schema: i suoi errori vengono ignorati
    def test_ignores_captcha(self):
        form = SampleForm(data=VALID_DATA)
        form.fields["captcha"] = fields.CaptchaField()
        result = validate_form(form)
        self.assertTrue(result["valid"])
        self.assertEqual(result["missing_fields"], [])