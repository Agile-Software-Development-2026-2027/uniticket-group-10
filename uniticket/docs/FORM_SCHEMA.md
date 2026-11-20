# Schema del form — SCRUM-94

`build_form_schema()` in `extensions/assistant/form_schema.py` legge il form Django di una tipologia di richiesta (`TicketCategoryModule.get_form()`) e lo descrive in JSON: campi, obbligatorietà, tipi, validazioni e valori iniziali. Non salva richieste e non valida le risposte.

```python
form = module.get_form(show_conditions=True, current_user=user)
schema = build_form_schema(form, category_id=module.ticket_category_id, module_id=module.pk)
```

Le tabelle di configurazione sono in `schema_field_config.py` (tipi dei campi, campi esclusi, limiti) e `schema_validator_config.py` (validator e controlli interni del form builder).

## Formato

```json
{"category_id": 42, "module_id": 15, "fields": [
  {"id": "codice", "label": "Codice", "type": "text", "required": true, "initial_value": null,
   "constraints": {"max_length": 7, "validators": [
     {"name": "RegexValidator", "message": "Inserisci un valore valido.", "pattern": "^[A-Z]+$",
      "flags": 0, "inverse_match": false},
     {"name": "MaxLengthValidator", "message": "...", "limit_value": 7}]}}
]}
```

Un campo disabilitato ha anche `disabled: true`. Una tabella ha tipo `array` e un elenco `fields` con le colonne. I campi composti mantengono gli ID dei sotto-campi creati da UniTicket. I CAPTCHA sono esclusi.

Gli allegati hanno tipo `file`: l'agente non li compila, ma deve dire all'utente quali caricare.

## Vincoli

| Campo | Chiavi in `constraints`, quando presenti |
|---|---|
| Tutti | `validators`: nome, messaggio e parametri di ogni validator Django |
| Testo, email, URL, IP | `min_length`, `max_length` (il limite più severo tra campo e validator) |
| Numeri | `min_value`, `max_value`, `max_digits`, `decimal_places`, `step_size` |
| Date e orari | `input_formats` |
| Scelte | `choices` (`value`, `label`), `max_choices` se maggiore di zero |
| Checkbox obbligatoria | `must_be_true` |
| Password | `pattern` |
| IP con subnet, MAC, numeri positivi, password | `custom_rule`: controllo scritto in `raise_error()` del form builder |
| Data iniziale/finale | `less_than_or_equal_to_field`: ID della data finale |
| Protocollo | `not_empty`, `max_date` (data corrente) |
| Tabella | `min_rows`, `max_rows`, `max_submitted_rows` |

Un tipo di campo non riconosciuto genera `NotImplementedError`, invece di una descrizione inventata.

## Test

```sh
docker compose run --build --rm -T --no-deps uniticket python manage.py test chatbot_tests.test_form_schema --settings=ticket_events.test_settings --noinput
```
