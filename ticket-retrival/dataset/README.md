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

## Revisione GT — 25 ottobre 2026

Il file attivo è `../evaluation_dataset.json`: 229 categorie e 2.061 richieste sintetiche (3 direct, 3 paraphrase, 3 indirect per categoria). Sono stati aggiunti gli esempi mancanti e precisati dipartimento, biblioteca, corso, bando o tipo di utente dove necessario. Non sono stati inseriti ID di risposta nei testi delle richieste.

I record che contenevano duplicati sono in fondo: `original_duplicate_queries` conserva i testi precedenti per confronto; il benchmark valuta soltanto `queries`, con il contesto aggiornato. `gt_review` segnala lo stato della revisione. Le 47 richieste ambigue sono spostate in fondo in record `review_group: ambiguous_gt`, con `ambiguity_group` e `target_category_ids`. Gli ID di origine possono ripetersi; i 9 esempi per categoria si contano sommando tutti i record. Il benchmark separa queste query dalle 2.014 single-target. Vedi [Ambiguità GT](../AMBIGUITA-GT.md).

La revisione non certifica tutte le GT. Prima di un confronto finale servono revisione umana e separazione sviluppo/test per gruppi di richieste equivalenti; il test non deve alimentare prompt, esempi del router o tuning. Le vecchie misure A0 non si riferiscono al dataset corrente.
