# Prova locale degli eventi TicketCategory

**Prototipo di verifica separato dalla UI ufficiale UniTicket.** Il laboratorio usa i modelli originali e un database SQLite dedicato. Il destinatario della notifica è fittizio.

## Stato dei tre flussi

| Flusso | Stato attuale |
|---|---|
| CREATE | Notifica di operazione e ID dopo commit, con gestione degli errori |
| UPDATE | Confronto di testo e otto metadata, notifica dopo commit solo quando cambiano i valori persistiti |
| DELETE | Notifica dell’ID dopo commit, anche per cancellazioni multiple e con cascata |

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

### UPDATE — implementato

```text
pre_save → lettura del vecchio stato con INDEX_FIELDS
  → salvataggio → post_save → lettura dei valori persistiti
  → dizionari uguali: nessuna notifica
  → dizionari diversi: dopo commit, safe_notify("UPDATE", category_id)
```

Il confronto legge entrambi gli stati dal database e rispetta `save(update_fields=...)`. Una modifica a qualsiasi campo di `INDEX_FIELDS` notifica `("UPDATE", category_id)` al destinatario. Salvataggi invariati o cambiamenti a campi esclusi non producono notifiche. Il componente destinatario ricostruirà il record completo.

Assegnare un altro ufficio con lo stesso nome produce UPDATE, perché cambia il suo ID. Rinominare struttura o ufficio lascia invece invariati gli ID e non produce notifiche. L’eliminazione dell’ufficio imposta l’ID a `None` tramite `SET_NULL`, senza chiamare `TicketCategory.save()`: i receiver sull’ufficio coprono anche questo percorso e notificano UPDATE per le categorie rimaste.

Il destinatario fittizio stampa `operation: "UPDATE"`, `category_id` e `delivery: "demo"`. Gli eventi vengono inviati soltanto dopo commit e gli errori del destinatario vengono registrati preservando il CRUD.

### DELETE — implementato

```text
TicketCategory.delete() → Django post_delete
  → cattura del category_id → transaction.on_commit()
  → safe_notify("DELETE", category_id) → destinatario dell’indice
```

Il receiver `category_deleted()` conserva l’ID prima che Django possa azzerarlo sull’istanza. La notifica non rilegge la categoria eliminata. Sono coperti `.delete()` e `QuerySet.delete()`, con una notifica per categoria anche quando vengono eliminati a cascata i moduli collegati.

Il destinatario fittizio stampa `operation: "DELETE"`, `category_id` e `delivery: "demo"`. Come per CREATE e UPDATE, rollback ed errori esterni vengono gestiti dopo il confine della transazione. Il destinatario definitivo dovrà accettare la rimozione di un ID già assente dall’indice. Ripetere una cancellazione locale tramite un queryset ormai vuoto non produce nuovi eventi.

I tre flussi usano ora lo stesso confine `safe_notify()` → `notify_index()` → destinatario configurabile. I precedenti `report()` e `handle_definition_event()` sono stati sostituiti da questo collegamento. `pre_delete` resta utilizzato sull’ufficio per rilevare gli UPDATE causati da `SET_NULL`.

Il receiver originale UniTicket per la pulizia degli allegati continua a essere eseguito. Nei test i percorsi sono temporanei; il rollback del database non ripristina eventuali file eliminati da quel receiver originale.

## Testo da embeddare e metadata

Il record futuro è `category_id + vector + metadata`. Il vettore sarà generato dal componente di indicizzazione usando soltanto `name` e `description`. La notifica corrente trasmette operazione e ID.

| Gruppo | Campi |
|---|---|
| `TEXT_FIELDS` | `name`, `description` |
| `METADATA_FIELDS` | `organizational_structure_id`, `organizational_office_id`, `allow_user`, `allow_employee`, `allow_anonymous`, `allow_guest`, `allow_spid_cie`, `is_active` |
| `INDEX_FIELDS` | Unione di testo e metadata confrontati durante UPDATE |

`organizational_office_id` può essere `None`. Anche le categorie inattive devono essere indicizzate con `is_active=False`. I metadata affiancano i controlli di autorizzazione Django.

I contratti sono in `extensions/ticket_events/interfaces.py` e `index_fields.py`. L’anteprima della demo mostra separatamente il testo con nome e descrizione e gli otto metadata. Gli ID organizzativi non vengono inseriti nel testo da embeddare. La generazione di vettori e il repository concreto appartengono ad altre task.

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

Aprire [localhost:8010](http://localhost:8010/) e premere **Crea tipologia**. Il terminale deve mostrare `CREATE`, l’ID e `delivery: "demo"`. Gli script eseguono Compose e mostrano gli eventi recenti e quelli nuovi. Per provare UPDATE cambiare nome, descrizione o uno dei checkbox nella sezione metadata, quindi salvare. Salvando gli stessi valori non deve comparire un nuovo evento. La demo consente di modificare i flag e l’ufficio; il cambio di struttura è verificato tramite ORM nei test. Premendo Elimina tipologia il terminale deve mostrare DELETE con il suo ID.

Dopo modifiche ai file Python, ricaricare il processo Django.

```powershell
docker compose -f compose.receiver-demo.yml restart lab
```

**Ctrl+C** interrompe i log. Per fermare il laboratorio conservando il suo database dedicato eseguire il comando seguente.

```powershell
docker compose -f compose.receiver-demo.yml down
```

## Eccezioni e transazioni CRUD

| Caso | Comportamento verificato |
|---|---|
| Categoria inattiva | Viene notificata sia alla creazione sia alla cancellazione; cambiare is_active produce UPDATE |
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

## TDD e verifiche degli incrementi

I test CREATE sono stati scritti prima dell’implementazione. La fase **RED** ha evidenziato l’assenza della notifica; la fase **GREEN** ha verificato il nuovo collegamento al destinatario fittizio.

Le fasi RED di UPDATE e DELETE hanno verificato l’assenza delle notifiche prima delle rispettive implementazioni. La suite corrente comprende **13 test CREATE**, **19 test UPDATE**, **13 test DELETE** e **2 test di regressione**, per un totale di **47**, usando SQLite in memoria e percorsi temporanei per gli allegati.

Le prove CREATE coprono notifica singola e ID corretto, categoria inattiva, callback differito e ID catturato, fixture, configurazione del notifier, errore con stack trace e risposta HTTP 201 preservata, commit reale, autocommit, rollback e savepoint.

Le verifiche UPDATE coprono tutti i dieci campi, modifiche multiple, assenza di cambiamenti, campi esclusi, `update_fields`, distinzione fra `None` e stringa vuota, fixture, errori del destinatario, commit, rollback, ID catturato e metadata booleani nell’API. Sono inoltre verificati rinomine senza evento, riassegnazione tra uffici omonimi e `SET_NULL`. I test confermano che `QuerySet.update()` aggira i signals.

Le prove DELETE coprono notifica singola, ID catturato, categoria inattiva, queryset multipli, queryset vuoto, cascata dei moduli, errori con stack trace e risposta API preservata, destinatario dimostrativo, commit reale, autocommit, rollback e savepoint.

### Struttura dei test

```text
extensions/ticket_events/
├── signals.py
├── notifications.py
├── content.py
├── test_settings.py
└── tests/
    ├── __init__.py
    ├── helpers.py
    ├── test_create_events.py
    ├── test_update_events.py
    ├── test_delete_events.py
    └── test_content.py
```

I casi di test sono separati dal codice applicativo. `helpers.py` contiene il destinatario fittizio e la preparazione condivisa. `test_settings.py` conserva la configurazione del database in memoria e dei percorsi temporanei.

Dalla cartella `uniticket`, eseguire soltanto i test DELETE.

```powershell
docker compose -f compose.receiver-demo.yml run --rm --no-deps lab "python3 manage.py test ticket_events.tests.test_delete_events --settings=ticket_events.test_settings --verbosity 1 --noinput"
```

Dalla cartella `uniticket`, eseguire soltanto i test UPDATE.

```powershell
docker compose -f compose.receiver-demo.yml run --rm --no-deps lab "python3 manage.py test ticket_events.tests.test_update_events --settings=ticket_events.test_settings --verbosity 1 --noinput"
```

Dalla cartella `uniticket`, eseguire soltanto i test CREATE.

```powershell
docker compose -f compose.receiver-demo.yml run --rm --no-deps lab "python3 manage.py test ticket_events.tests.test_create_events --settings=ticket_events.test_settings --verbosity 1 --noinput"
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
