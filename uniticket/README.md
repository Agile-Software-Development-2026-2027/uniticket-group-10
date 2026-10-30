## Avvio locale

Richiede Docker con Docker Compose.

Dalla root del repository:

```bash
cd uniticket
docker compose up --build
```

Apri http://localhost:8000.

## Accesso

Credenziali di prova per l’ambiente locale:

| Ruolo | Username | Password |
|---|---|---|
| Manager | `user1` | `secret1!` |
| Operatore | `user2` | `secret2!` |
| Utente normale | `utente` | `secret1!` |

## Arresto

```bash
docker compose down
```
## Demo API search

`POST /api/search` riceve `{"query": "..."}` e restituisce 5 ticket statici
nel formato `{"tickets": [{"id": 316, "title": "..."}, ...]}`.
Non consulta il database e non chiama un classificatore.

- Query `dipartimento` oppure `clarify`: restituisce `{"clarify": "Quale dipartimento ti interessa?", "quick_replies": ["DeMaCS", "DiMeS"]}`.
- Un clic su una quick reply invia il suo testo come nuova query e riceve i 5 ticket.
- Query `nessun risultato` oppure `no match`: restituisce `{"tickets": []}`.
- Qualsiasi altra query valida: restituisce gli stessi 5 ticket.

Aprire `/assistant` da autenticati e usare i pulsanti di esempio, oppure inviare
un messaggio. La chiamata è visibile nella scheda Network del browser.
Il mock richiede sessione e CSRF. I link usano ID della fixture locale;
l’accesso ai moduli resta controllato da UniTicket. La conversazione e le selezioni sono conservate nella scheda del browser
(sessionStorage), anche dopo refresh e apertura del modulo. “Nuova conversazione”
le cancella; la chiusura della scheda termina la conservazione.
