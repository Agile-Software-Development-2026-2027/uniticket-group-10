# TicketCategory — indicizzazione con Ollama e Qdrant

## 1. Cosa funziona

CREATE e UPDATE generano il vettore di una tipologia tramite il modello `snowflake-arctic-embed2` in Ollama e lo salvano in Qdrant con i metadata previsti. DELETE rimuove da Qdrant il punto con lo stesso ID della categoria e non chiama il modello.

Il repository usa `QDRANT_URL` (default `http://qdrant:6333`) e `QDRANT_COLLECTION` (default `ticket_categories`). Docker Compose configura l'URL per UniTicket e mantiene i dati Qdrant nel volume `qdrant-data`.

Questa indicizzazione non è ancora usata dalla ricerca dell'agente: `agent/app/retrieval.py` calcola embedding `bge-m3` e li mantiene in memoria. I vettori prodotti da `snowflake-arctic-embed2` non vanno confrontati con quelli di un modello diverso.

## 2. Flusso e file

```text
View originali UniTicket → save()/delete() → signal Django
    → signals.py: receiver e scelta di CategoryOperation
    → transaction.on_commit(...)
    → notifications.py: safe_notify(operation, category_id)
    → orchestrator.py: synchronize(operation, category_id)
        CREATE/UPDATE → content.py: snapshot(category_id, "default")
                      → embedding_text(category)
                      → provider.embed(text)
                      → embedder.py: SnowflakeEmbedder.embed(text)
                      → _finalEmbed([text]) → POST Ollama /api/embed
                      → vettore + metadata → database.repository: upsert()
        DELETE        → database.repository: delete(category_id)
```

| File | Responsabilità |
|---|---|
| `extensions/ticket_events/apps.py` | Importa i receiver all'avvio |
| `extensions/ticket_events/signals.py` | Rileva i cambiamenti e prenota la chiamata dopo il commit |
| `extensions/ticket_events/notifications.py` | Chiama l'orchestratore e registra gli errori |
| `extensions/ticket_events/orchestrator.py` | Legge il contenuto salvato, genera il vettore e coordina il repository |
| `extensions/ticket_events/content.py` | Legge i dati dal DB UniTicket e costruisce il testo |
| `extensions/ticket_events/interfaces.py` | Definisce l'enum e i contratti dei componenti |
| `extensions/embedder/embedder.py` | Invia il testo a Ollama e restituisce il vettore |
| `extensions/database/repository.py` | Crea la collection, esegue upsert/delete e supporta la ricerca in Qdrant |

`@receiver` collega una funzione a un signal e a un modello; `dispatch_uid` evita collegamenti duplicati. `pre_save` conserva il prima sull'istanza Python, `post_save` confronta i campi osservati. I salvataggi invariati non avviano l'orchestratore. L'eliminazione di un ufficio viene ascoltata separatamente per rilevare il collegamento che diventa nullo (`SET_NULL`).

`transaction.on_commit()` esegue la chiamata dopo il commit e la scarta al rollback. `safe_notify()` registra un eventuale errore del modello senza annullare il CRUD già confermato. Non esegue retry automatici.

## 3. Interfaccia e implementazione

`EmbeddingProvider` descrive la firma `embed(text) -> list[float]`; non contiene la richiesta HTTP. `SnowflakeEmbedder` la implementa.

In `orchestrator.py`:

```python
provider: EmbeddingProvider = SnowflakeEmbedder()
# Dentro synchronize(), dopo la lettura della categoria:
text = embedding_text(category)
vector = provider.embed(text)
```

Creare il provider non contatta Ollama. La richiesta parte con `embed()`, che chiama `_finalEmbed()` e restituisce il primo vettore della risposta. Il vettore e i metadata vengono poi passati a `IndexRepository.upsert()`; DELETE chiama `IndexRepository.delete()`.

`CategoryOperation` è un `StrEnum`: i receiver passano `CategoryOperation.CREATE`, `.UPDATE` o `.DELETE`; nei log restano i valori testuali. `IndexNotifier` descrive la chiamata con operazione e ID. `embed_query()` riguarda la ricerca e resta fuori da questo flusso.

## 4. Testo inviato e risultato

`snapshot()` legge dal database relazionale UniTicket, non da un database vettoriale. `synchronize()` usa la connessione `default` e i dati realmente salvati. Se la categoria non esiste più, termina senza chiamare il modello.

Il testo contiene soltanto `name + "\n" + description`:

```text
Assistenza Wi-Fi
Supporto nelle residenze
```

Una descrizione `None` diventa testo vuoto. I metadata restano separati: `organizational_structure_id`, `organizational_office_id`, `allow_user`, `allow_employee`, `allow_anonymous`, `allow_guest`, `allow_spid_cie`, `is_active`.

Il provider usa `http://host.docker.internal:11434/api/embed` e il modello `snowflake-arctic-embed2`, che restituisce 1024 valori. L'orchestratore salva il vettore e i metadata nella collection Qdrant. Anche una modifica ai soli metadata può avviare nuovamente la generazione: il confronto dei receiver continua a osservare tutti i campi previsti.

Se l'embedding fallisce, `safe_notify()` registra l'errore senza annullare il CRUD già confermato; non è previsto un retry automatico. Se la chiamata a Qdrant fallisce, l'errore è registrato nello stesso modo.

## 5. Test automatici

Dalla radice del repository, con Docker Desktop avviato:

```powershell
make test-local
```

Il comando costruisce l'immagine ed esegue i test dell'assistente e dei receiver con SQLite e Qdrant in memoria e file temporanei. Non avvia l'agent e non richiede Ollama o un servizio Qdrant. La prova con i servizi reali viene saltata per impostazione predefinita.

I test del repository e dell'orchestratore usano un client Qdrant in memoria e verificano creazione, sostituzione e rimozione del punto. I test dei signal verificano il commit/rollback e la persistenza del CRUD; le richieste HTTP a Ollama sono simulate. La prova reale seguente non sostituisce questi test.

## 6. Prova locale con Ollama reale

Avviare Docker Desktop e Ollama sull'host. `ollama list` deve mostrare `snowflake-arctic-embed2`; se manca, scaricarlo una volta con `ollama pull snowflake-arctic-embed2`. Avviare anche Qdrant:

```powershell
docker compose up -d qdrant
```

Dalla radice del repository, eseguire la prova con una collection dedicata:

```powershell
docker compose run --rm -T --no-deps `
  -e TICKET_EVENTS_LIVE_EMBEDDING=1 `
  -e QDRANT_COLLECTION=ticket_categories_live_test `
  uniticket python manage.py test ticket_events.tests.test_embedding_integration `
  --settings=ticket_events.test_settings --verbosity 1 --noinput
```

La prova è in `tests/test_embedding_integration.py`: crea una categoria temporanea, modifica la descrizione e la elimina. Attraversa signals, receiver, commit, `safe_notify()`, orchestratore, Ollama e Qdrant. Non passa dalle view/API. La collection dedicata evita che gli ID temporanei del database di test sovrascrivano o eliminino punti della collection usata dall'applicazione. Controllare i log: un errore del provider o di Qdrant appare come `Index notification failed` e non fa fallire automaticamente il CRUD di Django.

| Messaggio | Origine |
|---|---|
| `[ORCHESTRATION] operation=...` | Log permanente di `synchronize()` |
| JSON con operazione, modello, testo, dimensione e primi sei valori | Test: mostra il risultato reale |
| `Categoria indicizzata: ...` | Log permanente dopo l'upsert Qdrant |
| `DELETE: categoria temporanea...` | Test: nessuna chiamata al modello |
| `OK` e distruzione del database | Django: risultato e pulizia |

Il test usa SQLite in memoria e file temporanei; il database di test viene distrutto alla fine. La collection Qdrant di test resta nel volume `qdrant-data` (vuota dopo il DELETE) e può essere rimossa separatamente quando non serve più.

## 7. Limiti attuali

L'orchestratore delle categorie scrive e cancella i punti Qdrant, ma la ricerca dell'agente non interroga ancora questa collection. L'agente usa `bge-m3` e conserva i vettori delle categorie in memoria; per passare alla ricerca Qdrant occorre collegare esplicitamente il retriever e usare un modello di embedding coerente con quello usato per indicizzare.
