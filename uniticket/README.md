# Prova locale dei receiver

**Prototipo di verifica: non è la UI ufficiale UniTicket.** Usa i modelli e i signals originali, con un database dedicato alla demo. Nessun embedding viene generato.

## Cosa succede

```text
Pagina locale → crea / modifica / elimina una tipologia
    ↓
Modello originale UniTicket → .save() / .delete()
    ↓
Signals Django: pre_save / post_save / pre_delete / post_delete
    ↓
Nostri receiver: leggono i quattro dati prima e dopo
    ↓
report(): prepara l’evento e l’azione possibile
    ↓
Commit confermato → handle_definition_event()
    ↓
Terminale: [TICKET EVENT] + JSON
```

Azioni possibili: `INDEX`, `REINDEX`, `NONE`, `REMOVE`. Sono soltanto indicazioni nei log, non operazioni eseguite sugli embedding.

## Avvio

Con Docker Desktop aperto, dalla cartella `uniticket` esegui in PowerShell:

```powershell
.\demo-receivers.ps1
```

Apri [localhost:8010](http://localhost:8010/), poi crea, modifica ed elimina una tipologia fittizia. Il terminale mostra gli eventi recenti e quelli nuovi, con i quattro dati in `before` e `after`.

**Ctrl+C** interrompe i log; per fermare la demo:

```powershell
docker compose -f compose.receiver-demo.yml down
```

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
