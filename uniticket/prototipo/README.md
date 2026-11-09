# Prototipo UI per verificare i receiver

Questa cartella contiene soltanto strumenti di prova, separati dalla UI ufficiale e dal codice dei receiver.

```text
prototipo/
├── compose.yml                 # server locale, database dedicato e gateway
├── demo-receivers.ps1           # avvio e log puliti in PowerShell
├── demo-receivers.sh            # equivalente per Git Bash
├── proxy.py                    # inoltro locale verso il backend isolato
└── receiver_lab/
    ├── settings.py             # configurazione del laboratorio
    ├── test_settings.py        # database in memoria per i test
    ├── views.py / urls.py      # sola pagina di prova; CRUD nelle view originali
    ├── templates/              # grafica del prototipo
    ├── management/commands/    # creazione di manager e struttura locali
    └── tests/                  # test specifici del prototipo
```

Dalla cartella `uniticket`:

```powershell
.\prototipo\demo-receivers.ps1
```

Aprire http://localhost:8010/receiver-lab/, premere **Entra nel prototipo** e provare creazione, modifica e cancellazione. Le credenziali precompilate identificano solo il manager locale. Il terminale mostra i messaggi dei receiver.

```powershell
# Suite completa con SQLite in memoria.
docker compose -f prototipo/compose.yml run --rm --no-deps lab "python3 manage.py test ticket_events.tests receiver_lab.tests --settings=receiver_lab.test_settings --verbosity 1 --noinput"

# Arresto prima di rimuovere questa cartella; conserva i dati locali.
docker compose -f prototipo/compose.yml down
```

Il nome del progetto Docker e il volume sono invariati, quindi lo spostamento non azzera le tipologie di prova già create. Questa cartella non viene copiata dal Dockerfile nell’immagine dell’applicazione. Il codice da mantenere resta in `extensions/ticket_events/`.
