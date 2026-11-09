# TicketCategory — prototipo e test dei receiver

Il branch verifica il CRUD delle tipologie `TicketCategory`: view, form, permessi e modelli originali UniTicket; signals Django; nostri receiver raccolti in `extensions/ticket_events/signals.py`. Nessuna elaborazione degli embedding viene eseguita.

## Flusso

```text
Prototipo UI → view originale UniTicket → database locale → signal Django → nostri receiver

CREATE: category_add_new() → save() → pre_save / post_save(created=True)
UPDATE: category_edit() → save() → pre_save: stato precedente / post_save: confronto
DELETE: category_delete() → delete() → pre_delete: stato precedente / post_delete: ID eliminato
```

I receiver originali UniTicket restano attivi, incluso quello che pulisce gli allegati. Le view originali per ufficio e attivazione usano gli stessi modelli e signals. Per `SET_NULL` ascoltiamo anche l’eliminazione dell’ufficio.

## Prova manuale

Aprire Docker Desktop. Dalla cartella `uniticket`:

```powershell
.\prototipo\demo-receivers.ps1
```

In Git Bash: `bash prototipo/demo-receivers.sh`.

1. Aprire [il prototipo locale](http://localhost:8010/receiver-lab/).
2. Premere **Entra nel prototipo**. Le credenziali precompilate appartengono soltanto al manager locale: servono ai controlli di autorizzazione originali.
3. Creare una tipologia: nel terminale `CREATE` / `INDEX`.
4. Cambiare nome, descrizione o un flag e salvare: `UPDATE` / `REINDEX`.
5. Salvare senza cambiamenti: `UPDATE` / `NONE`, soltanto nel laboratorio.
6. Eliminare la tipologia: `DELETE` / `REMOVE`.

`possible_action` indica soltanto cosa potrebbe essere richiesto in futuro. Non genera né rimuove embedding.

Tutti i file specifici del prototipo sono in `prototipo/`, versionati per le prove del team e rimovibili insieme. Non modifica i template ufficiali e non implementa API CRUD: i form inviano alle view originali. Il solo `prototipo/compose.yml` prepara server, database e UI di prova; il Dockerfile dell’applicazione non lo copia nell’immagine.

Il laboratorio usa SQLite nel volume dedicato `demo-data`, file locali, email/cache in memoria, una rete backend interna e l’accesso browser su `127.0.0.1:8010`. Il comando di preparazione, anch’esso in `prototipo/`, crea solo struttura e manager di prova. Non usa account o database di server esterni.

## Messaggi nel terminale

Esempio: cambia soltanto la descrizione.

```json
{
  "signal": "post_save",
  "source_model": "TicketCategory",
  "category_id": 42,
  "operation": "UPDATE",
  "possible_action": "REINDEX",
  "before": {
    "name": "Assistenza Wi-Fi",
    "description": "Supporto nelle residenze",
    "organizational_structure_id": 1,
    "organizational_office_id": 2,
    "allow_user": true,
    "allow_employee": true,
    "allow_anonymous": false,
    "allow_guest": true,
    "allow_spid_cie": false,
    "is_active": true
  },
  "after": {
    "name": "Assistenza Wi-Fi",
    "description": "Supporto nelle aule",
    "organizational_structure_id": 1,
    "organizational_office_id": 2,
    "allow_user": true,
    "allow_employee": true,
    "allow_anonymous": false,
    "allow_guest": true,
    "allow_spid_cie": false,
    "is_active": true
  }
}
```

Per CREATE il precedente è `null`; per DELETE il successivo è `null`. Per UPDATE entrambi gli stati contengono tutti i campi osservati, inclusi i metadata invariati. Il confronto rileva il cambiamento, ma non riduce i dati del report. Il futuro indicizzatore rileggerà la categoria tramite ID per ricostruire il record completo; il contratto di notifica resta operazione + ID. I messaggi attendono il commit; un rollback li scarta. Il caso NONE è un messaggio diagnostico del laboratorio e non chiama il destinatario dell’indice.

## Campi osservati e formato del testo

| Gruppo | Campi |
|---|---|
| Testo | `name`, `description` |
| Metadata | `organizational_structure_id`, `organizational_office_id`, `allow_user`, `allow_employee`, `allow_anonymous`, `allow_guest`, `allow_spid_cie`, `is_active` |

`embedding_text()` restituisce `<name>\n<description>`, senza etichette:

```text
Assistenza Wi-Fi
Supporto nelle aule
```

I metadata restano fuori dal testo. Il confronto legge il database prima/dopo e rispetta `update_fields`. La notifica configurabile mantiene il contratto operazione + ID; il contesto del messaggio serve solo alla diagnostica.

## Test

Eliminare `prototipo/` non rimuove receiver, contratti o test dei percorsi originali. Il laboratorio Docker deve essere fermato prima della rimozione della cartella; il volume dei dati locali resta separato.

I test dei receiver e delle view originali sono in `extensions/ticket_events/tests/`; quelli del prototipo sono in `prototipo/receiver_lab/tests/`. Usano SQLite in memoria e allegati temporanei, senza richieste a server esterni.

```powershell
# Suite completa, incluso il prototipo condiviso.
docker compose -f prototipo/compose.yml run --rm --no-deps lab "python3 manage.py test ticket_events.tests receiver_lab.tests --settings=receiver_lab.test_settings --verbosity 1 --noinput"

# Soltanto i test del componente principale, usando il container come ambiente di esecuzione.
docker compose -f prototipo/compose.yml run --rm --no-deps lab "python3 manage.py test ticket_events.tests --settings=ticket_events.test_settings --verbosity 1 --noinput"
```

Sono verificati CRUD originale, campi rilevanti, dati invalidi, duplicati, permessi, CSRF, letture, rollback, uffici, pulizia originale degli allegati e messaggi ricevuti. Gli hook pre-commit e commit-msg vanno eseguiti prima del commit.

## Comandi utili e limiti

```powershell
# Ricaricare il processo dopo modifiche Python.
docker compose -f prototipo/compose.yml restart lab

# Leggere anche errori e stack trace esclusi dal filtro degli eventi.
docker compose -f prototipo/compose.yml logs --tail 100 lab

# Fermare il laboratorio conservando il database locale.
docker compose -f prototipo/compose.yml down
```

`Ctrl+C` ferma soltanto la visualizzazione dei log. Le fixture `raw=True` sono ignorate; `QuerySet.update()`, operazioni bulk e SQL diretto non emettono signals di salvataggio. L’eliminazione di un ufficio può produrre due UPDATE sulla stessa categoria: disattivazione e successivo scollegamento sono due cambiamenti reali. Rinominare struttura o ufficio non cambia gli ID osservati.

Restano valide le regole originali: attivare una tipologia richiede un ufficio e un modulo attivi; eliminarla è impedito se esistono richieste collegate. Un rollback non ripristina eventuali file già eliminati dal receiver originale. Nei test i file sono temporanei. Generazione embedding, consegna affidabile e ordinamento a valle appartengono ad altri ticket.

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
