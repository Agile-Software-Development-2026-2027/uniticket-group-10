# Schema del form — SCRUM-94

`build_form_schema()` in `extensions/assistant/form_schema.py` riusa il `serialize_form()` originale di UniTicket per descrivere il form di una tipologia di richiesta. Il nostro codice adatta il risultato al JSON concordato e aggiunge i vincoli mancanti. Non salva richieste e non valida le risposte.

```python
form = module.get_form(show_conditions=True, current_user=user)
schema = build_form_schema(form, category_id=module.ticket_category_id, module_id=module.pk)
```

Il flusso è: `TicketCategoryModule.get_form()` → `serialize_form()` di UniTicket → nostro adattamento → JSON.

`serialize_fields()` passa al serializer originale una copia del form e dei campi, senza CAPTCHA, con etichette e valori iniziali già risolti da Django. `serialize_field()` usa ID, etichetta, obbligatorietà, valore iniziale e stato disabilitato restituiti da UniTicket; aggiunge i vincoli ed esclude HTML e messaggi destinati alla grafica.

Le opzioni vengono riusate quando disponibili. Per radio button, widget personalizzati e gruppi non gestiti dal serializer, Django REST Framework le ricava dal campo. Manteniamo la traduzione dei tipi perché il serializer originale si basa sui widget; aggiungiamo anche le colonne delle tabelle e le regole tra sotto-campi. Il codice originale di UniTicket non viene modificato.

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

I test verificano anche la chiamata al vero serializer UniTicket, l'assenza di modifiche al form ricevuto e il mantenimento del JSON concordato.

```sh
docker compose run --build --rm -T --no-deps uniticket python manage.py test chatbot_tests.test_form_schema --settings=ticket_events.test_settings --noinput
```
