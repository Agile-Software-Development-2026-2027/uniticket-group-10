"""Verifica e valida l'aggiornamento di un singolo campo del form aperto."""

import json
from typing import Any

from django import forms
from django.core.serializers.json import DjangoJSONEncoder

from .form_schema import serialize_fields
from .form_validation import serialize_error


class UnknownFormFieldError(Exception):
    """Sollevata quando field_id non appartiene ai campi esposti dal form aperto."""


class DisabledFormFieldError(Exception):
    """Sollevata quando field_id corrisponde a un campo disabilitato."""


def check_updatable_field(form: forms.Form, field_id: str) -> dict:
    """Verifica che field_id appartenga allo schema del form aperto e sia modificabile."""
    fields_by_id = {field["id"]: field for field in serialize_fields(form)}
    field_schema = fields_by_id.get(field_id)
    if field_schema is None:
        raise UnknownFormFieldError(f"Il campo '{field_id}' non appartiene al form aperto.")
    if field_schema.get("disabled"):
        raise DisabledFormFieldError(f"Il campo '{field_id}' è disabilitato e non modificabile.")
    return field_schema


def validate_field_update(form: forms.Form, field_id: str, raw_value: Any) -> dict:
    """Valida il valore assegnato a field_id e restituisce il risultato strutturato."""
    form.is_valid()

    field_errors = form.errors.as_data().get(field_id, [])
    if field_errors:
        return {
            "valid": False,
            "field_id": field_id,
            "value": raw_value,
            "errors": [serialize_error(field_id, error) for error in field_errors],
        }

    normalized = form.cleaned_data.get(field_id, raw_value)
    normalized = json.loads(json.dumps(normalized, cls=DjangoJSONEncoder))

    return {
        "valid": True,
        "field_id": field_id,
        "value": normalized,
        "errors": [],
    }