
# UniTicket

## Eventi TicketCategory

I receiver permanenti osservano creazione, modifica ed eliminazione delle tipologie.
Dopo il commit chiamano l'orchestratore, che registra INDEX, REINDEX o REMOVE.
Il provider Snowflake è incluso; questa PR non lo collega all'orchestratore e non usa un database vettoriale.
Il prototipo UI è stato rimosso.

Il flusso e i campi osservati sono descritti in [FLUSSO_TICKET_CATEGORY.md](docs/FLUSSO_TICKET_CATEGORY.md).

Dalla radice del repository, con Docker Desktop avviato:

```powershell
docker compose build uniticket
docker compose run --rm --no-deps uniticket python manage.py test ticket_events.tests --settings=ticket_events.test_settings --noinput
```

I test usano SQLite in memoria e file temporanei; non richiedono Ollama o un database vettoriale.
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
