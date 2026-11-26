"""valida i dati compilati dall'agente con le regole originali del form di uniTicket"""


from django import forms
from .schema_field_config import EXCLUDED_FIELDS



def serialize_error(field_id,error) -> dict:
    return{
        "field": None if field_id==forms.forms.NON_FIELD_ERRORS else field_id,
        "code": error.code or "invalid",
        "message": " ".join(error.messages),
    }


def validate_form(form: forms.Form) -> dict:
    form.is_valid()

    missing_fields=[]
    errors=[]

    for field_id, field_errors in form.errors.as_data().items():
        if isinstance(form.fields.get(field_id),EXCLUDED_FIELDS):
            continue

        for error in field_errors:
            if error.code=="required":
                missing_fields.append(field_id)
            else:
                errors.append(serialize_error(field_id,error))

    return{
        "valid": not missing_fields and not errors,
        "missing_fields": missing_fields,
        "errors": errors,
    }



