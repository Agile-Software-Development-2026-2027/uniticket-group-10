"""Legge il form UniTicket e prepara il JSON, senza salvare o validare risposte."""

import json
from copy import copy

from django import forms
from django.core import validators
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone
from django_form_builder import dynamic_fields
from rest_framework import serializers
from uni_ticket.dynamic_form import serialize_form

from .schema_field_config import EXCLUDED_FIELDS, FIELD_LIMITS, FIELD_TYPES
from .schema_validator_config import CUSTOM_RULES, LIMIT_VALIDATORS, VALIDATOR_ATTRS

# Elimina soltanto i valori None: zero e False vengono conservati
def without_none(values: dict) -> dict:
    return {name: value for name, value in values.items() if value is not None}

# Cerca il campo nel dizionario: prima la sua classe, poi quelle da cui deriva
def lookup_by_class(field: forms.Field, mapping: dict):
    for field_class in type(field).__mro__:
        if field_class in mapping:
            return mapping[field_class]
    return None

# Restituisce il tipo JSON del campo, per esempio "email"
def field_type(field: forms.Field) -> str:
    schema_type = lookup_by_class(field, FIELD_TYPES)
    if schema_type is None:
        raise NotImplementedError(type(field).__name__)
    return schema_type

# Legge i parametri del validator senza controllare una risposta dell'utente
def serialize_validator(validator) -> dict:
    # Il nome dice quale controllo è, per esempio "MaxLengthValidator" o "validate_ipv4_address".
    details = {
        "name": getattr(validator, "__name__", type(validator).__name__),
        "message": getattr(validator, "message", None),
    }
    if isinstance(validator, validators.BaseValidator):
        limit = validator.limit_value
        details["limit_value"] = limit() if callable(limit) else limit
    for validator_class, attrs in VALIDATOR_ATTRS.items():
        if isinstance(validator, validator_class):
            for attr in attrs:
                details[attr] = getattr(validator, attr, None)
    if isinstance(validator, validators.RegexValidator):
        details["pattern"] = validator.regex.pattern
        details["flags"] = validator.regex.flags
    return without_none(details)

# Conserva il limite più restrittivo tra quello del campo e quello del validator
def add_validator_limit(constraints: dict, validator, limit) -> None:
    for validator_class, (key, stricter) in LIMIT_VALIDATORS.items():
        if isinstance(validator, validator_class):
            constraints[key] = stricter(constraints.get(key, limit), limit)
            return

# Legge lunghezze, limiti numerici, formati e validator del campo Django
def standard_constraints(field: forms.Field) -> dict:
    constraints = without_none({name: getattr(field, name, None) for name in FIELD_LIMITS})
    if hasattr(field, "input_formats"):
        constraints["input_formats"] = list(field.input_formats)
    if field.validators:
        constraints["validators"] = []
        for validator in field.validators:
            details = serialize_validator(validator)
            constraints["validators"].append(details)
            add_validator_limit(constraints, validator, details.get("limit_value"))
    return constraints

# Indica che una checkbox obbligatoria deve essere accettata
def must_be_true(field: forms.Field) -> dict:
    is_checkbox = isinstance(field, forms.BooleanField) and not isinstance(field, forms.NullBooleanField)
    return {"must_be_true": True} if is_checkbox and field.required else {}


# Riusa le opzioni del serializer originale e adatta i casi non gestiti
def choice_options(field: forms.Field, serialized_field: dict) -> dict:
    if not isinstance(field, forms.ChoiceField) or isinstance(field, dynamic_fields.CustomComplexTableField):
        return {}
    options = serialized_field["options"]
    # UniTicket omette le opzioni di alcuni widget e non appiattisce tutti i gruppi.
    if not options or any(isinstance(option["text"], (list, tuple)) for option in options):
        choices = serializers.ChoiceField(choices=field.choices).choices
        options = [{"value": value, "text": label} for value, label in choices.items()]
    return {"choices": [{"value": option["value"], "label": option["text"]} for option in options]}

# Legge il massimo delle selezioni, solo se il campo multiplo ha un limite
def max_choices(field: forms.Field) -> dict:
    limit = getattr(field, "max_permitted", None) or 0
    if isinstance(field, forms.MultipleChoiceField) and limit > 0:
        return {"max_choices": limit}
    return {}

# Descrive il controllo che il form builder scrive in raise_error()
def custom_rule(field: forms.Field) -> dict:
    description = lookup_by_class(field, CUSTOM_RULES)
    return {"custom_rule": description} if description else {}

# Legge la regex già impostata sul campo password
def password_pattern(field: forms.Field) -> dict:
    if isinstance(field, dynamic_fields.CustomPasswordField):
        return {"pattern": field.PASSWORD_SEC_REGEX}
    return {}

# Legge le regole che collegano i sotto-campi, per esempio data iniziale e finale
def parent_rules(field: forms.Field) -> dict:
    parent = getattr(field, "parent", None)
    constraints = {}
    if isinstance(parent, dynamic_fields.DateStartEndComplexField) and field is parent.start:
        constraints["less_than_or_equal_to_field"] = parent.end.name
    if isinstance(parent, dynamic_fields.ProtocolloField):
        constraints["not_empty"] = True
        if field is parent.data:
            constraints["max_date"] = timezone.localdate()
    return constraints

# Riunisce i vincoli del campo chiamando esplicitamente ogni funzione
def field_constraints(field: forms.Field, serialized_field: dict) -> dict:
    constraints = standard_constraints(field)
    constraints.update(must_be_true(field))
    constraints.update(choice_options(field, serialized_field))
    constraints.update(max_choices(field))
    constraints.update(custom_rule(field))
    constraints.update(password_pattern(field))
    constraints.update(parent_rules(field))
    return constraints

# Legge colonne e limiti sulle righe dal formset originale della tabella
def table_details(name: str, field: forms.Field) -> tuple[list[dict], dict]:
    formset = field.widget.formset
    if formset is None:
        raise ValueError(f"{name}: configurazione della tabella non valida")
    constraints = {"max_submitted_rows": formset.absolute_max}
    # Django controlla min_num solo se validate_min è attivo, altrimenti non conta.
    min_rows = max(int(field.required), formset.min_num if formset.validate_min else 0)
    if min_rows:
        constraints["min_rows"] = min_rows
    if formset.validate_max:
        constraints["max_rows"] = formset.max_num
    return serialize_fields(formset.empty_form), constraints

# Adatta il campo serializzato da UniTicket e aggiunge i vincoli mancanti
def serialize_field(bound_field, serialized_field: dict) -> dict:
    field = bound_field.field
    try:
        schema_type = field_type(field)
    except NotImplementedError as error:
        raise NotImplementedError(f"{bound_field.name}: {error}") from error
    initial_value = serialized_field["initial"]
    if isinstance(field, dynamic_fields.CustomHiddenField) and initial_value is None:
        initial_value = field.widget.attrs.get("value")
    # Seleziona i dati utili del serializer originale: l'HTML resta fuori dal JSON.
    result = {
        "id": serialized_field["id"],
        "label": serialized_field["label"],
        "type": schema_type,
        "required": serialized_field["required"],
        "constraints": field_constraints(field, serialized_field),
        "initial_value": initial_value,
    }
    if serialized_field["disabled"]:
        result["disabled"] = True
    if schema_type == "array":
        result["fields"], table_constraints = table_details(bound_field.name, field)
        result["constraints"].update(table_constraints)
    return result

# Chiama il serializer originale su una copia del form, escludendo i CAPTCHA
def serialize_fields(form: forms.Form) -> list[dict]:
    # La copia esclude i CAPTCHA prima che UniTicket ne provi a generare l'HTML.
    schema_form = copy(form)
    schema_form.fields = {}
    for bound_field in form:
        if isinstance(bound_field.field, EXCLUDED_FIELDS):
            continue
        field = copy(bound_field.field)
        # Django risolve etichetta e valore iniziale; il serializer legge questi attributi.
        field.label = bound_field.label
        field.initial = bound_field.initial
        schema_form.fields[bound_field.name] = field
    serialized_fields = serialize_form(schema_form)
    return [
        serialize_field(form[serialized_field["id"]], serialized_field)
        for serialized_field in serialized_fields
    ]


# Riunisce gli ID e i campi, usando Django per convertire date e altri valori nel JSON
def build_form_schema(form: forms.Form, *, category_id: int, module_id: int) -> dict:
    schema = {
        "category_id": category_id,
        "module_id": module_id,
        "fields": serialize_fields(form),
    }
    return json.loads(json.dumps(schema, cls=DjangoJSONEncoder))
