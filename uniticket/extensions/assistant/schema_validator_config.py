"""Descrizioni dei controlli originali e parametri letti dai validator Django."""

from django.core import validators
from django_form_builder import dynamic_fields


# Verifiche interne che il form builder esegue in raise_error(), descritte a parole.
CUSTOM_RULES = {
    dynamic_fields.CustomIP4MaskedField: "Formato IPv4 con subnet opzionale verificato dal form builder.",
    dynamic_fields.CustomMACField: "Formato MAC verificato dal form builder.",
    dynamic_fields.PositiveIntegerField: "Il valore convertito viene controllato come sequenza di sole cifre.",
    dynamic_fields.PositiveFloatField: "Il formato del valore numerico convertito viene controllato dal form builder.",
    dynamic_fields.CustomPasswordField: "La password deve rispettare PASSWORD_SEC_REGEX del campo.",
}

# Per ogni tipo di validator, gli attributi da copiare nello schema.
# Un validator può prendere più righe: un URLValidator è anche un
# RegexValidator, quindi gli si copiano sia "schemes" sia "inverse_match".
VALIDATOR_ATTRS = {
    validators.DecimalValidator: ("max_digits", "decimal_places"),
    validators.StepValueValidator: ("offset",),
    validators.EmailValidator: ("domain_allowlist",),
    validators.URLValidator: ("schemes",),
    validators.RegexValidator: ("inverse_match",),
}

# Validator che fissano un minimo o un massimo.
# Per ognuno: il nome del vincolo e come scegliere tra il limite del campo
# e quello del validator. Per un minimo si tiene il più alto (max), per un
# massimo il più basso (min), così vale sempre il limite più severo.
LIMIT_VALIDATORS = {
    validators.MinLengthValidator: ("min_length", max),
    validators.MaxLengthValidator: ("max_length", min),
    validators.MinValueValidator: ("min_value", max),
    validators.MaxValueValidator: ("max_value", min),
}
