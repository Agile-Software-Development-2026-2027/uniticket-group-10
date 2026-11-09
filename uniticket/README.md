# Prova locale degli eventi TicketCategory

**Prototipo di verifica separato dalla UI ufficiale UniTicket.** Il laboratorio usa i modelli originali e un database SQLite dedicato. Il destinatario della notifica è fittizio.

## Stato dei tre flussi

| Flusso | Stato attuale |
|---|---|
| CREATE | Notifica di operazione e ID dopo commit, con gestione degli errori |
| UPDATE | Log dimostrativi precedenti; confronto dei nuovi metadata e notifica UPDATE da implementare |
| DELETE | Log dimostrativi precedenti; notifica DELETE da implementare |

### CREATE — implementato

```text
TicketCategory.save(), anche con is_active=False
  → Django post_save(created=True) → category_saved()
  → transaction.on_commit()
  → safe_notify("CREATE", category_id)
  → notify_index() → destinatario configurato
```

Il destinatario fittizio predefinito produce questo log.

```text
[TICKET EVENT] {
  "operation": "CREATE",
  "category_id": 42,
  "delivery": "demo"
}
```

`TICKET_EVENTS_NOTIFIER` accetta una funzione, un oggetto invocabile come `FakeNotifier`, oppure un percorso Python. La configurazione seguente seleziona il destinatario locale predefinito.

```python
TICKET_EVENTS_NOTIFIER = "ticket_events.notifications.log_notification"
```

### UPDATE — progetto del prossimo incremento

```text
pre_save → lettura del vecchio stato con INDEX_FIELDS
  → salvataggio → post_save → lettura dei valori persistiti
  → dizionari uguali: nessuna notifica
  → dizionari diversi: dopo commit, safe_notify("UPDATE", category_id)
```

La lettura dal database rispetterà anche `save(update_fields=...)`. Il componente destinatario ricostruirà il record completo. Oggi il prototipo stampa ancora `UPDATED / REINDEX` o `UNCHANGED / NONE` confrontando i quattro dati precedenti. Il nuovo confronto sui metadata sarà implementato insieme a UPDATE.

### DELETE — progetto di un incremento successivo

```text
TicketCategory.delete() → Django post_delete
  → cattura del category_id → transaction.on_commit()
  → safe_notify("DELETE", category_id) → destinatario dell’indice
```

Oggi resta disponibile il log dimostrativo `DELETED / REMOVE`. Il futuro destinatario dovrà accettare anche la rimozione di un ID già assente dall’indice.

## Testo da embeddare e metadata

Il record futuro è `category_id + vector + metadata`. Il vettore sarà generato dal componente di indicizzazione usando soltanto `name` e `description`. La notifica corrente trasmette operazione e ID.

| Gruppo | Campi |
|---|---|
| `TEXT_FIELDS` | `name`, `description` |
| `METADATA_FIELDS` | `organizational_structure_id`, `organizational_office_id`, `allow_user`, `allow_employee`, `allow_anonymous`, `allow_guest`, `allow_spid_cie`, `is_active` |
| `INDEX_FIELDS` | Unione di testo e metadata da confrontare nel futuro UPDATE |

`organizational_office_id` può essere `None`. Anche le categorie inattive devono essere indicizzate con `is_active=False`. I metadata affiancano i controlli di autorizzazione Django.

I contratti sono in `extensions/ticket_events/interfaces.py` e `index_fields.py`. L’anteprima del prototipo conserva ancora i nomi di struttura e ufficio e sarà allineata insieme a UPDATE. Quei nomi sono esclusi dal nuovo `TEXT_FIELDS`. La generazione di vettori e il repository concreto appartengono ad altre task.

## Avvio dell’incremento grafico

Aprire Docker Desktop. Dalla root del repository entrare nella cartella `uniticket`.

```powershell
cd uniticket
```

In PowerShell avviare il laboratorio e i log degli eventi.

```powershell
.\demo-receivers.ps1
```

In Git Bash il comando equivalente è `bash demo-receivers.sh`.

Aprire [localhost:8010](http://localhost:8010/) e premere **Crea tipologia**. Il terminale deve mostrare `CREATE`, l’ID e `delivery: "demo"`. Gli script eseguono Compose e mostrano gli eventi recenti e quelli nuovi. Modifica ed eliminazione continuano a produrre i log dimostrativi indicati sopra.

Dopo modifiche ai file Python, ricaricare il processo Django.

```powershell
docker compose -f compose.receiver-demo.yml restart lab
```

**Ctrl+C** interrompe i log. Per fermare il laboratorio conservando il suo database dedicato eseguire il comando seguente.

```powershell
docker compose -f compose.receiver-demo.yml down
```

## Eccezioni e transazioni CREATE

| Caso | Comportamento verificato |
|---|---|
| Categoria inattiva | Viene notificata come CREATE |
| Transazione aperta | La notifica attende il commit |
| Autocommit | La callback viene eseguita subito |
| Rollback, anche di un savepoint | La relativa notifica viene scartata |
| Istanza modificata prima del callback | Viene usato l’ID catturato alla creazione |
| Fixture con `raw=True` | La notifica viene ignorata durante il caricamento |
| Errore del destinatario o configurazione non invocabile | Errore, operazione, ID e stack trace nei log; il CRUD già riuscito viene preservato |

Il filtro degli script mostra gli eventi. Per consultare anche errori e stack trace, leggere i log completi.

```powershell
docker compose -f compose.receiver-demo.yml logs --tail 100 lab
```

Retry, recupero dei fallimenti e ordine delle elaborazioni concorrenti restano da concordare. `on_commit()` lega la notifica al commit ma non costituisce una coda persistente. Scritture con `QuerySet.update()`, operazioni bulk e SQL diretto richiedono una verifica specifica perché aggirano i normali signals di salvataggio.

## TDD e verifiche di questo incremento

I test CREATE sono stati scritti prima dell’implementazione. La fase **RED** ha evidenziato l’assenza della notifica; la fase **GREEN** ha verificato il nuovo collegamento al destinatario fittizio.

Sono passati **13 test CREATE** e **7 test di regressione**, per un totale di **20**, usando SQLite in memoria e percorsi temporanei per gli allegati.

Le prove CREATE coprono notifica singola e ID corretto, categoria inattiva, callback differito e ID catturato, fixture, configurazione del notifier, errore con stack trace e risposta HTTP 201 preservata, commit reale, autocommit, rollback e savepoint.

Dalla cartella `uniticket`, eseguire soltanto i test CREATE.

```powershell
docker compose -f compose.receiver-demo.yml run --rm --no-deps lab "python3 manage.py test ticket_events.test_create_events --settings=ticket_events.test_settings --verbosity 1 --noinput"
```

Per eseguire la suite completa usare il comando seguente.

```powershell
docker compose -f compose.receiver-demo.yml run --rm --no-deps lab "python3 manage.py test ticket_events --settings=ticket_events.test_settings --verbosity 1 --noinput"
```

Ogni incremento funzionale comprende i test dei nuovi comportamenti, l’implementazione minima, la regressione, l’aggiornamento di questo README e gli hook pre-commit e commit-msg.

<details>
<summary>Istruzioni dell’applicazione standard, separata dalla demo</summary>

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

</details>
