# TicketCategory — collegamento al modello di embedding

## 1. Cosa funziona

CREATE e UPDATE generano il vettore di una tipologia tramite il modello `snowflake-arctic-embed2` in Ollama. DELETE non chiama il modello.

Il collegamento è permanente. Il vettore viene ricevuto dall'orchestratore, ma non viene ancora salvato: il repository vettoriale sarà un incremento separato.

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
                      → vettore → log della dimensione
        DELETE        → termina senza leggere la categoria o generare vettori
```

| File | Responsabilità |
|---|---|
| `extensions/ticket_events/apps.py` | Importa i receiver all'avvio |
| `extensions/ticket_events/signals.py` | Rileva i cambiamenti e prenota la chiamata dopo il commit |
| `extensions/ticket_events/notifications.py` | Chiama l'orchestratore e registra gli errori |
| `extensions/ticket_events/orchestrator.py` | Legge il contenuto salvato e chiama il provider |
| `extensions/ticket_events/content.py` | Legge i dati dal DB UniTicket e costruisce il testo |
| `extensions/ticket_events/interfaces.py` | Definisce l'enum e i contratti dei componenti |
| `extensions/embedder/embedder.py` | Invia il testo a Ollama e restituisce il vettore |

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

Creare il provider non contatta Ollama. La richiesta parte con `embed()`, che chiama `_finalEmbed()` e restituisce il primo vettore della risposta. L'implementazione del modello resta invariata.

`CategoryOperation` è un `StrEnum`: i receiver passano `CategoryOperation.CREATE`, `.UPDATE` o `.DELETE`; nei log restano i valori testuali. `IndexNotifier` descrive la chiamata con operazione e ID, senza aggiungere passaggi. `IndexRepository` descrive il futuro salvataggio e la rimozione, ma non è ancora chiamato. `embed_query()` riguarda la ricerca e resta fuori da questo flusso.

## 4. Testo inviato e risultato

`snapshot()` legge dal database relazionale UniTicket, non da un database vettoriale. `synchronize()` usa la connessione `default` e i dati realmente salvati. Se la categoria non esiste più, termina senza chiamare il modello.

Il testo contiene soltanto `name + "\n" + description`:

```text
Assistenza Wi-Fi
Supporto nelle residenze
```

Una descrizione `None` diventa testo vuoto. I metadata restano separati: `organizational_structure_id`, `organizational_office_id`, `allow_user`, `allow_employee`, `allow_anonymous`, `allow_guest`, `allow_spid_cie`, `is_active`.

Il provider usa `http://host.docker.internal:11434/api/embed` e il modello `snowflake-arctic-embed2`, che restituisce 1024 valori. L'orchestratore registra ID e dimensione, senza salvare il vettore. Anche una modifica ai soli metadata può avviare nuovamente la generazione: il confronto dei receiver continua a osservare tutti i campi previsti.

## 5. Test automatici

Dalla radice del repository, con Docker Desktop avviato:

```powershell
make test-local
```

Il comando costruisce l'immagine ed esegue i test dell'assistente e dei receiver con SQLite in memoria e file temporanei. Non avvia l'agent e non richiede Ollama. La prova con il modello reale viene saltata per impostazione predefinita.

`tests/test_orchestrator.py` contiene cinque test: azioni CRUD, chiamata diretta da `safe_notify()`, DELETE/categoria assente, testo salvato inviato dal provider e fallimento del modello dopo il commit. Il provider esegue il suo codice; soltanto HTTP è simulato. Le verifiche dell'errore preservano la categoria già salvata. Il test del testo è stato verificato prima senza collegamento (RED), poi con il collegamento (GREEN).

## 6. Prova locale con Ollama reale

Avviare Docker Desktop e Ollama. `ollama list` deve mostrare `snowflake-arctic-embed2`; se manca, scaricarlo una volta con `ollama pull snowflake-arctic-embed2`.

Dopo `make test-local`, dalla radice del repository:

```powershell
docker compose run --rm -T --no-deps -e TICKET_EVENTS_LIVE_EMBEDDING=1 uniticket python manage.py test ticket_events.tests.test_embedding_integration --settings=ticket_events.test_settings --verbosity 1 --noinput
```

La prova è in `tests/test_embedding_integration.py`: crea una categoria temporanea, modifica la descrizione e la elimina. Attraversa signals, receiver, commit, `safe_notify()`, orchestratore e provider. Non passa dalle view/API. La richiesta HTTP raggiunge Ollama reale; il test osserva la chiamata senza simulare la risposta.

| Messaggio | Origine |
|---|---|
| `[ORCHESTRATION] operation=...` | Log permanente di `synchronize()` |
| JSON con operazione, modello, testo, dimensione e primi sei valori | Test: mostra il risultato reale |
| `Embedding generato: ...` | Log permanente di `synchronize()` |
| `DELETE: categoria temporanea...` | Test: nessuna chiamata al modello |
| `OK` e distruzione del database | Django: risultato e pulizia |

Prova reale eseguita con esito positivo il 12 novembre 2026. La suite automatica ha eseguito 57 test con successo e saltato questa singola prova facoltativa.

La prova verifica due vettori validi e diversi da 1024 valori; DELETE non genera embedding. Usa soltanto SQLite in memoria e file temporanei, senza modificare categorie esistenti. Il database di test viene distrutto alla fine.

## 7. Prossimo incremento

Collegare il repository: CREATE/UPDATE salveranno il vettore e tutti i metadata con `upsert(category_id, vector, metadata)`; DELETE userà `delete(category_id)`. Questo incremento non include Qdrant né il collegamento al database vettoriale.
