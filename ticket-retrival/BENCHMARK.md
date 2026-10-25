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

Il benchmark valuta richieste **single-label**: per ogni query è previsto un solo ID di categoria corretto.
Le metriche sono calcolate sia globalmente sia per tipologia di query (`direct`, `paraphrase`, `indirect`).

- **Hit@1, Hit@5, Hit@10:** quota delle query per cui la categoria corretta compare entro i primi K risultati.
- **Top-1 Accuracy (`top1_accuracy`):** quota delle query con categoria corretta al primo posto; coincide con Hit@1.
- **Recall@1, Recall@5, Recall@10:** nell'attuale valutazione single-label coincidono numericamente con Hit@K (non rappresentano una macro-recall tra categorie).
- **MRR@5:** media dell'inverso della posizione della prima categoria corretta entro le prime cinque; metrica storica mantenuta nei report.
- **Latenza (`latency_ms`):** media, mediana e p95 dei tempi di `search()` e di validazione del risultato, espressi in millisecondi.
- **Errori (`errors`):** eccezioni durante la ricerca o risultati non validi.
- **Astensioni (`abstentions`):** assenza di risultati senza errori.

Errori e astensioni restano nel denominatore e valgono come mancati successi.
La preparazione iniziale del prototipo è misurata separatamente (`initialization_ms`).

**Metriche da valutare in futuro:** Median Rank, P90 Rank e P95 Rank. Queste non sono ancora implementate e richiedono di definire come trattare le categorie assenti dalla Top-K.

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

## 5. Controlli e riproducibilità

Il benchmark esteso include:

- **Validazione dell'input:** rifiuto di Ground Truth non presenti nel catalogo e query vuote o non valide.
- **Validazione dell'output:** rilevazione di ID sconosciuti o duplicati e punteggi non finiti.
- **`coverage`:** conteggio delle categorie coperte dal dataset e identificativi delle categorie senza query.
- **`cases`:** dettagli delle predizioni, posizione della categoria corretta, latenza ed eventuale classe di errore per ogni richiesta.
- **`experiment`:** percorsi, parametri CLI espliciti, versione Python e SHA-256 del catalogo e del dataset.

Il protocollo usa fino a 10 candidati per query, non applica warm-up o retry e include la prima ricerca nel calcolo delle latenze. Gli hash identificano i file utilizzati, ma per la riproducibilità completa occorre registrare anche commit, modello, parametri e ambiente.

Un prototipo che restituisce un solo ID non produce una vera Top-5 o Top-10: in quel caso la Top-1 è la misura primaria della classificazione. Non sono ancora previsti Ground Truth multi-label né casi in cui l'astensione sia considerata corretta.

**Risultati delle esecuzioni:** [RISULTATI-BENCHMARK.md](RISULTATI-BENCHMARK.md).

### Test automatici

Dalla cartella `ticket-retrival`:

```bash
uv run python -m unittest discover -s tests -v
```
