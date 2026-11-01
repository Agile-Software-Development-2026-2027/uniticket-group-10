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

## Dipendenze frontend: npm e Vite

Vue e HTMX sono dichiarati in `package.json`; `package-lock.json` blocca le versioni.
Non vengono conservate copie manuali in `static/vendor/`.

L’avvio rimane `docker compose up --build`: uno stage Node esegue `npm ci` e
`npm run build`, poi copia gli asset nel runtime Django. Node non serve sul computer
per questo avvio e non viene eseguito nel container Django finale.

Per verificare o sviluppare la build anche sul computer, dalla cartella `uniticket`,
con Node.js >= 22.12:

```bash
npm ci
npm test
npm run build
```

Vite genera `frontend-dist/assistant.js` e `assistant.css`. Django li espone come
`/static/assistant_dist/…`; i template Vue restano nell’HTML e la build include il compilatore.
`node_modules/` e `frontend-dist/` sono esclusi da Git.

Con la configurazione Docker attuale, dopo modifiche a JavaScript, CSS o dipendenze,
eseguire nuovamente `docker compose up --build` e ricaricare il browser. Il solo
`npm run build` sul computer non aggiorna gli asset già inclusi nell’immagine Docker.
Python e template mantengono il mount di sviluppo esistente.
