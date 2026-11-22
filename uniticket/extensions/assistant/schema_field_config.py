"""Tipi JSON dei campi, campi esclusi dallo schema e limiti letti dai campi."""

from django import forms
from django_form_builder import dynamic_fields


# Tipo JSON di ogni classe di campo. La ricerca segue la MRO, quindi vince
# sempre la classe più specifica e l'ordine delle righe non conta.
FIELD_TYPES = {
    dynamic_fields.CustomComplexTableField: "array",
    dynamic_fields.CustomIP4MaskedField: "ipv4_network",
    dynamic_fields.CustomMACField: "mac_address",
    dynamic_fields.CustomPasswordField: "password",
    dynamic_fields.CustomHiddenField: "hidden",
    dynamic_fields.PositiveIntegerField: "integer",
    forms.MultipleChoiceField: "multiple_choice",
    forms.ChoiceField: "choice",
    forms.BooleanField: "boolean",
    forms.DecimalField: "number",
    forms.FloatField: "number",
    forms.IntegerField: "integer",
    forms.DateTimeField: "datetime",
    forms.DateField: "date",
    forms.TimeField: "time",
    forms.EmailField: "email",
    forms.URLField: "url",
    forms.GenericIPAddressField: "ip_address",
    forms.CharField: "text",
    # L'agente non carica allegati: li segnala all'utente, che li aggiunge da sé.
    forms.FileField: "file",
}

# I campi tecnici del CAPTCHA non fanno parte dello schema.
EXCLUDED_FIELDS = (dynamic_fields.CaptchaField, dynamic_fields.CaptchaHiddenField)

# Limiti del campo da copiare nello schema. Se il campo non li ha, vengono saltati.
FIELD_LIMITS = (
    "min_length",
    "max_length",
    "min_value",
    "max_value",
    "max_digits",
    "decimal_places",
    "step_size",
)
