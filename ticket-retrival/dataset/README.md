# TODO
- Generare un nuovo dataset che comprenda i campi del form e una descrizione testuale per ogni ticket.
- Generare una descrizione testuale per ogni ticket in modo che possiamo valutare un nuovo prototipo.

## Disclaimer
Prevalentemente vibe coded questa parte... tanto è un prototipo.

# Generazione del dataset di valutazione

Questa cartella contiene gli strumenti per generare query realistiche a partire
dai metadati delle categorie ticket, da usare nel benchmark dei prototipi di retrieval.

Per ogni ticket, un LLM riceve titolo, descrizione e struttura organizzativa e genera
**9 query**:

- 3 `direct`: richieste che esprimono esplicitamente il servizio desiderato.
- 3 `paraphrase`: lo stesso bisogno espresso con parole e costruzioni diverse.
- 3 `indirect`: richieste che descrivono una situazione da cui emerge il bisogno.

Il risultato include anche `description_quality`, che indica se la descrizione è
`informative`, `partially_informative` o `uninformative`. Le query devono essere
non vuote e distinte; il risultato viene validato prima di essere salvato.

Al momento i campi del form non vengono passati al modello: le query generate
non tengono quindi conto delle loro label, opzioni o obbligatorietà.


## Configurazione
Il file [generate.yaml](generate.yaml) seleziona il backend e i suoi parametri:

- `openai`: usa un endpoint compatibile con le API OpenAI, anche locale.
- `codex`: usa il backend Codex tramite il relativo SDK.

Impostare `backend: openai` oppure `backend: codex` e configurare il modello.

Ti consiglio di usare backend codex se hai un abbonamento a ChatGPT. Altrimenti valuta l'utilizzo di openai (ci dovrebbe essere google ai studio che dava token gratis)

## Generare query d'esempio

```bash
uv run python dataset/generation/generate_queries.py
```

## Generare query per tutti i ticket

```bash
uv run python dataset/generate_dataset.py tickets.json \
  --output evaluation_dataset_nuovo.json \
  --parallel 2
```

L'input è una lista di categorie con `ticket_category_id`, `title`, `description`
e `structure`. Titolo e ID
sono obbligatori; la struttura può essere un oggetto con `name` oppure una stringa.

- `--output`: file JSON di destinazione; il default è `evaluation_dataset.json`.
- `--parallel`: numero massimo di richieste simultanee; il default è `1`.
- `--config`: percorso di una configurazione alternativa a `dataset/generate.yaml`.

Se cambi prompt o configurazione del modello, scegli un nuovo file di output!

## Risorse correlate
- [Dataset di valutazione disponibile](../evaluation_dataset.json)
- [Definizione del benchmark e metriche](../BENCHMARK.md)
- [Prompt di generazione](generation/GENERATION_PROMPT.md)
- [Configurazione dei backend](generate.yaml)

## Test

## TODO
- Aggiungere test sulla qualità delle query prodotte dal prompt.
