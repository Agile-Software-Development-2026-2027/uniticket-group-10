
# UniTicket

## Eventi TicketCategory

I receiver permanenti osservano creazione, modifica ed eliminazione delle tipologie.
Dopo il commit chiamano l'orchestratore: CREATE e UPDATE generano l'embedding di nome e descrizione tramite il provider Snowflake; DELETE non chiama il modello.
Il modello è raggiunto tramite Ollama. Il salvataggio nel database vettoriale non è ancora implementato.
Il prototipo UI è stato rimosso.

Il flusso e i campi osservati sono descritti in [FLUSSO_TICKET_CATEGORY.md](docs/FLUSSO_TICKET_CATEGORY.md).

Dalla radice del repository, con Docker Desktop avviato:

```powershell
docker compose build uniticket
docker compose run --rm --no-deps uniticket python manage.py test ticket_events.tests --settings=ticket_events.test_settings --noinput
```

I test automatici usano SQLite in memoria, file temporanei e risposte HTTP simulate: non richiedono Ollama o un database vettoriale. La prova facoltativa con Ollama reale e i relativi comandi sono nel documento del flusso.
La CI e l'hook pre-commit eseguono `make test-local`: include sia `chatbot_tests` sia `ticket_events.tests`, senza avviare l'agent.

## Partial page update
<p align="center">
  <img src="../_images/partial-page-update.png" alt="Overview" width="800">
</p>

## Accesso

Credenziali di prova per l’ambiente locale:

| Ruolo | Username | Password |
|---|---|---|
| Manager | `user1` | `secret1!` |
| Operatore | `user2` | `secret2!` |
| Utente normale | `utente` | `secret1!` |
