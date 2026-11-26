"""Test unitari sull'aggiornamento e la validazione di un singolo campo del form."""

from django import forms
from django.test import SimpleTestCase
from django_form_builder import dynamic_fields as fields

from assistant.form_update import (
    DisabledFormFieldError,
    UnknownFormFieldError,
    check_updatable_field,
    validate_field_update,
)


class SampleUpdateForm(forms.Form):
    nome = forms.CharField(max_length=10)
    email = forms.EmailField()
    sede = forms.ChoiceField(choices=[("aula", "Aula"), ("residenza", "Residenza")])
    bloccato = forms.CharField(disabled=True, required=False)


class FormUpdateTests(SimpleTestCase):
    def test_accepts_field_belonging_to_form(self):
        field = check_updatable_field(SampleUpdateForm(), "email")
        self.assertEqual(field["id"], "email")

    def test_rejects_unknown_or_excluded_field(self):
        form = SampleUpdateForm()
        form.fields["captcha"] = fields.CaptchaField()

        for field_id in ("inesistente", "captcha"):
            with self.subTest(field_id=field_id):
                with self.assertRaises(UnknownFormFieldError):
                    check_updatable_field(form, field_id)

    def test_rejects_disabled_field(self):
        with self.assertRaises(DisabledFormFieldError):
            check_updatable_field(SampleUpdateForm(), "bloccato")

    def test_validates_single_field_ignoring_other_missing_required_fields(self):
        form = SampleUpdateForm(data={"email": "mario@unical.it"})
        result = validate_field_update(form, "email", "mario@unical.it")
        self.assertEqual(
            result,
            {"valid": True, "field_id": "email", "value": "mario@unical.it", "errors": []},
        )

    def test_returns_field_error_when_value_is_invalid(self):
        form = SampleUpdateForm(data={"email": "mario@"})
        result = validate_field_update(form, "email", "mario@")
        self.assertFalse(result["valid"])
        self.assertEqual(result["field_id"], "email")
        self.assertEqual(result["errors"][0]["code"], "invalid")