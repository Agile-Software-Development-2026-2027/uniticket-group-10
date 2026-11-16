
# UniTicket

## Eventi TicketCategory

I receiver permanenti osservano creazione, modifica ed eliminazione delle tipologie.
Dopo il commit chiamano l'orchestratore: CREATE e UPDATE generano l'embedding di nome e descrizione con `snowflake-arctic-embed2` tramite Ollama e salvano vettore e metadata nella collection Qdrant `ticket_categories`; DELETE rimuove il punto senza chiamare il modello.
Con Docker Compose l'app usa Qdrant all'indirizzo interno `http://qdrant:6333` e raggiunge Ollama sull'host tramite `http://host.docker.internal:11434`. Per eseguire il flusso reale, avviare Ollama con il modello disponibile e il servizio Qdrant.
L'indicizzazione CRUD non è ancora usata dalla ricerca dell'agente: quest'ultima calcola embedding in memoria con `bge-m3`.
Il prototipo UI è stato rimosso.

Il flusso e i campi osservati sono descritti in [FLUSSO_TICKET_CATEGORY.md](docs/FLUSSO_TICKET_CATEGORY.md).

Dalla radice del repository, con Docker Desktop avviato:

```powershell
docker compose build uniticket
docker compose run --rm --no-deps uniticket python manage.py test ticket_events.tests --settings=ticket_events.test_settings --noinput
```

I test automatici usano SQLite e Qdrant in memoria, file temporanei e risposte HTTP simulate: non richiedono Ollama o un servizio Qdrant. La prova facoltativa con Ollama e Qdrant reali, inclusa una collection isolata per il test, è descritta nel documento del flusso.
La CI e l'hook pre-commit eseguono `make test-django`: include sia `chatbot_tests` sia `ticket_events.tests`, senza avviare l'agent.

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

## Dashboard Qdrant locale

Dalla radice del repository: `docker compose up -d qdrant`.
Aprire [Qdrant Dashboard](http://localhost:6333/dashboard), quindi **Collections** e la collezione da esaminare. Nei punti sono visibili ID, vettore e payload (metadata).
La porta è accessibile solo dal PC locale. La prova automatica elimina la propria collezione alla fine, quindi non lascia record da consultare nel dashboard.
