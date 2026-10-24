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
- **MRR@5 (Mean Reciprocal Rank at 5):** misura quanto in alto viene posizionato il ticket corretto nei primi 5 risultati. Per ogni query viene assegnato un punteggio pari a `1 / posizione` del primo risultato corretto (0 se non compare nei primi 5). La media costituisce l'MRR@5.

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

