# TicketCategory — flusso attuale e prossimi passi

## 1. Dove siamo

Gestiamo gli eventi di creazione, modifica ed eliminazione delle **tipologie** UniTicket (`TicketCategory`), non le richieste compilate dagli utenti.

**Oggi:** riceviamo i signals, aspettiamo il commit e chiamiamo l’orchestratore. L’orchestratore sceglie e stampa INDEX, REINDEX o REMOVE. **Non genera ancora vettori e non aggiorna un indice.**

## 2. Flusso permanente, con file e funzioni

```text
uni_ticket/views/manager.py — view originali UniTicket
  category_add_new() / category_edit() / category_delete()
      ↓ save() / delete()
Django emette pre_save, post_save, pre_delete, post_delete
      ↓
extensions/ticket_events/signals.py — receiver nostri
      ↓ transaction.on_commit(...)
Commit riuscito
      ↓
notifications.py: safe_notify(operation, category_id)
      ↓
notifications.py: notify_index(operation, category_id)
      ↓ chiamata diretta
orchestrator.py: synchronize(operation, category_id)
      ↓
Stampa l’azione scelta, poi termina
```

`apps.py`, con `TicketEventsConfig.ready()`, importa `signals.py` all’avvio e registra i receiver.

La chiamata tra notifiche e orchestratore è solo questa:

```python
from .orchestrator import synchronize

def notify_index(operation: CategoryOperation, category_id: int) -> None:
    synchronize(operation, category_id)
```

## 3. Cosa fanno i receiver

| Caso | Funzioni in signals.py | Risultato dopo il commit |
|---|---|---|
| Creazione | `category_before()` → `category_saved(created=True)` | `safe_notify("CREATE", id)` |
| Modifica | `category_before()` → `category_saved(created=False)` | UPDATE solo se cambiano i campi osservati |
| Salvataggio invariato | `category_saved()` confronta prima e dopo | Nessuna chiamata all’orchestratore |
| Eliminazione | `category_deleted()` | `safe_notify("DELETE", id)` |
| Eliminazione ufficio | `office_deleting()` → `office_deleted()` | UPDATE per le categorie che perdono il collegamento |

`snapshot()` in `content.py` legge dal DB di UniTicket i campi elencati in `index_fields.py`. Il confronto usa i valori realmente salvati, anche con `save(update_fields=...)`.

Eliminando un ufficio, il collegamento nelle categorie diventa nullo (`SET_NULL`) senza chiamare `TicketCategory.save()`: per questo ascoltiamo anche l’ufficio. La struttura usa invece PROTECT. Rinominare struttura o ufficio non cambia gli ID osservati.

Esempio: la categoria 42 passa dalla descrizione “Supporto nelle residenze” a “Supporto nelle aule”. Il receiver confronta i due stati e, dopo il commit, avvia `safe_notify("UPDATE", 42)`.

### Come leggere la firma di un receiver

```python
@receiver(pre_save, sender=TicketCategory,
          dispatch_uid="ticket_events.category_before")
def category_before(sender, instance, using, raw=False, **kwargs):
    ...
```

| Elemento | Significato |
|---|---|
| `@receiver` | Collega la funzione a un signal e a un modello |
| `dispatch_uid` | Evita di registrare due volte lo stesso collegamento |
| `sender` | Classe del modello, per esempio `TicketCategory` |
| `instance` | Singola categoria coinvolta nell’operazione |
| `using` | Nome della connessione DB usata, normalmente `"default"` |
| `raw` | Indica un caricamento speciale di dati da fixture: viene ignorato |
| `**kwargs` | Accetta gli altri argomenti inviati da Django |
| `created` nel post_save | True per una nuova riga, False per un aggiornamento |

`STATE` è il nome dell’attributo temporaneo che contiene il prima sull’oggetto Python. Non è una colonna del DB:

```python
setattr(instance, STATE, before)       # Conserva il prima sull’oggetto.
getattr(instance, STATE, None)         # Lo legge, oppure restituisce None se manca.
hasattr(instance, STATE)              # Controlla se l’attributo esiste.
delattr(instance, STATE)              # Lo rimuove dopo averlo letto.
```

## 4. Commit, notifiche e orchestratore

```python
transaction.on_commit(partial(safe_notify, "UPDATE", instance.pk), using=using)
```

`partial()` prepara la chiamata fissando operazione e ID. Django la esegue al commit e la scarta al rollback. Senza transazione aperta la esegue subito. `post_save` indica che la scrittura è avvenuta, non che la transazione sia già confermata.

`safe_notify()` chiama `notify_index()` dentro un try/except. Se la chiamata fallisce, scrive nei log errore, operazione e ID. Il CRUD già confermato resta valido; non ci sono retry automatici.

`synchronize()` attualmente fa soltanto questa scelta:

| Operazione | Azione scelta | Esecuzione attuale |
|---|---|---|
| CREATE | INDEX | Stampa la scelta |
| UPDATE | REINDEX | Stampa la scelta |
| DELETE | REMOVE | Stampa la scelta |

Esempio di log: `[ORCHESTRATION] operation=UPDATE category_id=42 action=REINDEX`. Significa che la funzione è stata raggiunta e ha scelto l’azione; non che il vettore sia stato aggiornato.

## 5. Interfacce e dati da usare dopo

Le interfacce sono in `interfaces.py`. Descrivono come chiamare i componenti; non eseguono passaggi aggiuntivi.

| Interfaccia | Cosa descrive | Stato |
|---|---|---|
| `IndexNotifier` | Chiamata con operazione e ID | Contratto conservato; la chiamata attuale è diretta a synchronize |
| `EmbeddingProvider` | `embed(text)` restituisce `list[float]` | Il provider Snowflake del collega esiste, ma questo flusso non lo chiama |
| `IndexRepository` | `upsert(id, vector, metadata)` e `delete(id)` | Contratto conservato; repository non collegato |

`embed_query()` riguarda le ricerche e resta fuori da questo flusso.

Testo previsto: `name + "\n" + description`, senza etichette o metadata. I metadata sono separati: `organizational_structure_id`, `organizational_office_id`, `is_active`, `allow_user`, `allow_employee`, `allow_anonymous`, `allow_guest`, `allow_spid_cie`.

## 6. Test permanenti

Tutti i test sono in `extensions/ticket_events/tests/`, separati dai file applicativi. Usano i modelli e le view originali UniTicket con SQLite in memoria e file temporanei. Non modificano dati di server esterni e non chiamano il modello di embedding.

La suite è stata accorpata: 37 test con esempi raggruppati per operazione, mantenendo le verifiche della ricezione e dei percorsi originali. Il confronto prima/dopo del riordino mostra le stesse 139 righe applicative permanenti esercitate. Tutti i 37 test passano anche senza rete.

| File | Test | Funzionalità verificate |
|---|---|---|
| `test_crud_events.py` | 8 | CREATE/UPDATE/DELETE, categorie attive e inattive, attesa del commit, ID conservato, fixture, errori, cancellazioni multiple, cascata, autocommit, rollback e savepoint |
| `test_update_events.py` | 8 | Tutti i campi osservati, più modifiche insieme, campi esclusi, update_fields, descrizione nulla/vuota, uffici e limiti di QuerySet.update |
| `test_official_views.py` | 17 | CRUD HTTP originale, form invalidi e duplicati, permessi, letture, attivazione, assegnazione/rimozione/eliminazione ufficio, rollback, registrazione unica e allegati |
| `test_content.py` | 2 | Campi degli snapshot, valori nulli e testo nome/descrizione |
| `test_orchestrator.py` | 2 | Azione scelta per tutto il CRUD e chiamata diretta da notify_index |

`helpers.py` prepara i dati locali; `post_and_commit()` evita di ripetere il blocco del POST con le callback. Nei test della ricezione `unittest.mock.patch` intercetta la funzione importata: non servono impostazioni aggiuntive nel codice applicativo.

## 7. Comandi per verificare il codice

La CI esegue `make test-local`, che avvia insieme i test dell'assistente (`chatbot_tests`) e dei receiver (`ticket_events.tests`) con `ticket_events.test_settings`: 54 test, SQLite in memoria e file temporanei. Non richiede Ollama o un database vettoriale. Lo stesso comando è usato dall'hook pre-commit.

Dalla radice del repository, con Docker Desktop avviato e il submodule upstream inizializzato:

```powershell
# Costruisce l’immagine con il codice permanente.
git submodule update --init --recursive
docker compose build uniticket

# Esegue i 37 test con DB in memoria e file temporanei, senza chiamare servizi esterni.
docker compose run --rm --no-deps uniticket python manage.py test ticket_events.tests --settings=ticket_events.test_settings --verbosity 1 --noinput

# Esegue soltanto i due test dell’orchestratore.
docker compose run --rm --no-deps uniticket python manage.py test ticket_events.tests.test_orchestrator --settings=ticket_events.test_settings --verbosity 1 --noinput
```

I test verificano il codice attuale: la scelta dell’azione è implementata, l’esecuzione della sincronizzazione ancora no. Il collegamento diretto è stato verificato RED → GREEN. Prima del commit vanno eseguiti anche gli hook del repository.

## 8. Prossimi incrementi

| Passo | Cosa implementare per tutto il CRUD | Verifica nei test |
|---|---|---|
| 1. Provider | CREATE/UPDATE leggono la categoria, costruiscono il testo e chiamano EmbeddingProvider; DELETE usa solo l’ID | Verifica del testo e delle chiamate con funzioni di prova; integrazione locale separata con il modello di embedding |
| 2. Repository | CREATE inserisce, UPDATE sostituisce, DELETE rimuove tramite IndexRepository | Repository fittizio limitato ai test, con record per ID e metadata completi |
| 3. Repository reale | Collega l’implementazione del repository reale mantenendo lo stesso contratto | Verifica con un’istanza locale di prova |

Il comportamento finale atteso, ripreso dal precedente documento di orchestrazione, è:

```text
CREATE / UPDATE → rilettura della categoria dal DB
                → nome + a capo + descrizione
                → provider.embed(text)
                → repository.upsert(category_id, vector, metadata completi)
DELETE          → repository.delete(category_id), senza generare vettori
```

L’ID resta stabile; UPDATE deve sostituire tutto il record, inclusi metadata invariati, falsi o nulli. Le ripetizioni non devono creare duplicati. Se una rilettura trova la categoria già eliminata, non deve ricrearne il record. Questi comportamenti futuri andranno implementati e testati: non sono attivi oggi.



## 9. Cosa fa ora

L’incremento attuale copre **CRUD → signals → receiver → commit → notify_index → synchronize → scelta dell’azione**.
