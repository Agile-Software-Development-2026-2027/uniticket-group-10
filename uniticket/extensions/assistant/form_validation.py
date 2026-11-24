"""valida i dati compilati dall'agente con le regole originali del form di uniTicket"""


from django import forms
from .schema_field_config import EXCLUDED_FIELDS


# questo metodo trasforma un errore django in un dizionario leggibile dall'agente (JSON)
# esempio di cosa può contenere form.errors.as_data():
# {"telefono": [ValidationError(["Inserisci un valore valido."], code="invalid")]} con il serialize diventa
# {"field": "telefono", "code": "invalid", "message": "Inserisci un valore valido."}
def serialize_error(field_id,error) -> dict:
    return{
        # se gli errori riguardano il form intero field si imposta a None, se riguarda un singolo campo si imposta all'id del campo
        # form.errors = {
          #  "telefono": ["Inserisci un valore valido."],
         #   "__all__":  ["La data di inizio deve essere precedente alla data di fine."],
        #}
        # diventa
        # "errors": [
        #   {"field": "telefono", "code": "invalid", "message": "Inserisci un valore valido."},
        #   {"field": null, "code": "invalid", "message": "La data di inizio deve essere precedente alla data di fine."}
        #  ]
        # questo perchè Se mandassi all'agente "field": "__all__", l'agente potrebbe pensare che esista un campo chiamato __all__ e provare a compilarlo con set_field("__all__", ...), che non esiste. 
        # Con None il significato è chiaro: questo errore riguarda il form in generale, leggi il messaggio.
        "field": None if field_id==forms.forms.NON_FIELD_ERRORS else field_id,
        "code": error.code or "invalid",
        "message": " ".join(error.messages),
    }


def validate_form(form: forms.Form) -> dict:
    form.is_valid()

    missing_fields=[]
    errors=[]

    #scorre solo i field con errori
    for field_id, field_errors in form.errors.as_data().items():
        if isinstance(form.fields.get(field_id),EXCLUDED_FIELDS):
            continue

        for error in field_errors:
            if error.code=="required":
                missing_fields.append(field_id)
            else:
                errors.append(serialize_error(field_id,error))

    return{
        # è valido se non ci sono campi mancanti e errori, non guardiamo gli allegati
        "valid": not missing_fields and not errors,
        "missing_fields": missing_fields,
        "errors": errors,
    }



