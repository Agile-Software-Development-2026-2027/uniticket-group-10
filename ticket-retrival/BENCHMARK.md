# Definizione del benchmark
Il benchmark ha l'obiettivo di confrontare le prestazioni dei diversi prototipi di retrieval, utilizzando lo stesso insieme di query e le stesse metriche di valutazione.

### 1. Dataset di test
Un insieme di query realistiche che simulino le richieste degli utenti.

È stato generato un [dataset di test](evaluation_dataset.json) sulla base del titolo e della descrizione del ticket. Le query non hanno quindi contesto riguardo ai campi presenti nel form.

È possibile generare nuove query attraverso [generate_dataset.py](dataset/generate_dataset.py).

Risorse correlate al dataset:

- [Documentazione del dataset](dataset/README.md)
- [Documentazione della generazione delle query](dataset/generation/README.md)
- [Prompt usato per generare le query](dataset/generation/GENERATION_PROMPT.md)
- [Configurazione del backend](dataset/generate.yaml)

### 2. Prototipi
Per capire come funziona il benchmark ti consiglio di leggere la [documentazione dei prototipi](retrival/README.md).

### 3. Metriche di valutazione

Il benchmark valuta ogni prototipo attraverso le seguenti metriche:

- **Hit@K (Hit Rate at K):** misura la percentuale di query per cui il ticket corretto compare tra i primi K risultati, indipendentemente dalla posizione. Ad esempio, Hit@5 = 0.90 significa che nel 90% delle query il ticket corretto compare tra i primi 5 risultati.
- ~~**MRR@5 (Mean Reciprocal Rank at 5):** misura quanto in alto viene posizionato il ticket corretto nei primi 5 risultati. Per ogni query viene assegnato un punteggio pari a `1 / posizione` del primo risultato corretto (0 se non compare nei primi 5). La media costituisce l'MRR@5.~~

**Le metriche attuali non vanno bene.**

#### TODO: Metriche da considerare:
- Median Rank: mediana della posizione del ticket corretto. Permette di valutare la prestazione tipica, risultando meno sensibile ai rank estremi rispetto alla media dei rank.
- P90 / P95 Rank: percentili della distribuzione dei rank. Indicano entro quale posizione viene recuperato il ticket corretto per almeno il 90% o il 95% delle query, evidenziando le difficoltà nella coda della distribuzione.

## 4. Far girare il benchmark su un prototipo

```bash
uv run python benchmark.py --help
```
Usa --help per vedere quali parametri sono disponibili

```bash
uv run python benchmark.py --prototype custom_prototype.py --help
```
Usa `--prototype` e `--help` per vedere quali parametri sono disponibili (definiti da `custom_prototype.py` nel costruttore, il parametro `tickets` viene iniettato in automatico).

```bash
uv run python benchmark.py --prototype retrival/prototypes/dense.py --help
```

Per eseguire il benchmark:

```bash
uv run python benchmark.py --prototype retrival/prototypes/dense.py --eval-set good_evaluation_dataset.json > risultati_dense.json
```

# TODO
- Benchmark multi-lingue (inglese, spagnolo, ...)
- Trovare un prototipo che permetta il multi-lingua



## Estensione del 25 ottobre 2026 — protocollo single-label

Restano `hit@1`, `hit@5`, `hit@10` e `mrr@5`. Nuovi campi, sia globali sia
per tipo di query:

- `top1_accuracy`: frazione di richieste con prima categoria corretta.
- `recall@1`, `recall@5`, `recall@10`: con UN SOLO ID corretto per query
  coincidono con i rispettivi Hit@K. Non sono macro-recall per categoria.
- `latency_ms`: numero osservazioni, media, mediana e p95 (nearest-rank).
  Misura `search(query, k=10)` e la validazione del risultato, anche sui fallimenti.
- `errors`: eccezioni o output non validi; `abstentions`: lista vuota senza errore.
  Entrambi rimangono nel denominatore e valgono come mancati successi.

La preparazione del modello/indice è riportata separatamente in `initialization_ms`.
Non include gli import, e può includere download/cache del costruttore. Non ci sono
warm-up o retry automatici: la prima ricerca è inclusa. Per confronti affidabili
ripetere le esecuzioni e annotare hardware, device e stato della cache.

`coverage` segnala categorie senza query. `cases` conserva risultati per caso con
indice della query, tipo, ID atteso, predizioni ed eventuale classe di errore.
`experiment` conserva hash dei due input, percorso prototipo, parametri CLI espliciti
e versione Python. I default non esplicitati vanno ricondotti alla versione del codice:
registrare anche commit/modello/prompt per gli esperimenti definitivi.

ID inventati, duplicati e score non finiti rendono la prova un errore. Ground truth
fuori catalogo viene rifiutata. Il protocollo non implementa ancora etichette multiple
né valuta l'astensione come risposta corretta; concordarli prima di estenderlo.
Un classificatore con un unico ID non ha una graduatoria Top-5: le metriche vengono
calcolate sull'output disponibile e non vanno interpretate come retrieval di 5 candidati.

Verifica su Windows, dalla cartella `ticket-retrival`:

```powershell
.\.venv-bm25\Scripts\python.exe -m unittest discover -s tests -v
```

Report locali della verifica conservati in `results.local/bm25-before-20261025-111038.json`
e `results.local/bm25-after-20261025-111159.json`. Tutte le metriche preesistenti,
anche per tipo di query, sono identiche. Nessuna modifica a catalogo o dataset.
