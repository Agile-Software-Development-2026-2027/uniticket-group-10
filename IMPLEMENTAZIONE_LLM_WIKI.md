# Implementazione di una vera LLM Wiki

> [!NOTE]
> **Stato: non in programma, conservato come riferimento.**
>
> Oggi l'unica fonte è il catalogo, quindi una wiki non aggiungerebbe informazioni nuove. L'unica
> parte con un effetto misurato, il linguaggio degli utenti per ogni modulo, esiste già in forma
> molto più semplice in `form_phrases.json`, e anche quel beneficio non è dimostrato.
>
> Da riconsiderare solo se si aggiungono **nuove fonti di conoscenza**, come regolamenti, FAQ o
> ticket reali. La sola crescita del catalogo, anche con l'esportazione ufficiale, non basta.
>
> Il piano è precedente alla riscrittura: `taxonomy.json`, citato nel testo, è stato rimosso.
> Le sezioni 2 e 3 (revisione delle modifiche, fonti obbligatorie) e la 5 (feedback
> degli utenti) restano le idee più utili da recuperare.

## Obiettivo

Evolvere l'attuale tassonomia statica in una vera LLM Wiki nello stile del
pattern descritto da Karpathy: una base di conoscenza persistente, leggibile
da persone, composta da pagine semantiche collegate e mantenuta da un agente
LLM con fonti, lint, versionamento e approvazione delle modifiche.

L'architettura attuale:

```text
raw_cache → uniticket.json → taxonomy.json → retrieval
```

diventerebbe:

```text
raw_cache/
    ↓
wiki/                  ← conoscenza persistente mantenuta dall'LLM
    ↓
taxonomy.json/index    ← artefatti compilati per il runtime
    ↓
retrieval + router
```

## Differenza rispetto all'implementazione attuale

Oggi `taxonomy.json` è un indice semantico generato deterministicamente dal
catalogo. È una buona base tecnica, ma non è ancora una vera LLM Wiki perché
non contiene pagine persistenti curate dall'LLM, non conserva revisioni e non
ha un ciclo di ingestione, aggiornamento e approvazione.

## 1. Livello persistente `wiki/`

Struttura iniziale suggerita:

```text
wiki/
├── _schema.md
├── services/
│   ├── wifi-access.md
│   ├── esse3-exam-booking.md
│   └── ...
├── domains/
│   ├── didactics.md
│   ├── taxes.md
│   └── ...
├── families/
│   ├── exam-management.md
│   └── ...
├── structures/
│   └── ict.md
├── concepts/
│   ├── spid.md
│   ├── erasmus.md
│   └── ...
└── _changelog/
```

Ogni pagina dovrebbe avere frontmatter strutturato:

```yaml
---
id: service:ict-wifi-access
type: service
status: active
source_slugs:
  - ict-wifi-access
source_schema_hash: "..."
confidence: high
last_verified: 2026-10-30
related:
  - concept:wifi
  - structure:ict
  - domain:connectivity
---
```

Il contenuto dovrebbe descrivere:

- cosa risolve il servizio;
- formulazioni tipiche degli studenti;
- quando usarlo e quando non usarlo;
- servizi simili o facilmente confondibili;
- struttura responsabile;
- fonti precise nel catalogo o nei file raw;
- eventuali contraddizioni;
- relazioni verso altre pagine.

## 2. Agente di ingestione e manutenzione

Aggiungere un comando come:

```bash
python3 scripts/update_wiki.py
```

Flusso:

1. rilevare modifiche in `raw_cache/` o `uniticket.json`;
2. individuare le pagine wiki coinvolte;
3. fornire all'LLM dati precedenti e nuovi;
4. aggiornare le pagine esistenti o crearne di nuove;
5. aggiungere collegamenti tra concetti e servizi;
6. citare sempre la fonte;
7. segnalare conflitti invece di risolverli arbitrariamente;
8. produrre un diff da approvare.

L'LLM non dovrebbe scrivere direttamente nel runtime. Dovrebbe modificare le
pagine wiki; uno script deterministico dovrebbe poi compilare le pagine in
`taxonomy.json` e negli indici di retrieval:

```text
raw_cache + wiki modificata
          ↓
lint
          ↓
build_taxonomy.py
          ↓
taxonomy.json + indici runtime
```

## 3. Regole di affidabilità

Il file `wiki/_schema.md` dovrebbe stabilire almeno queste regole:

- nessuna informazione senza fonte;
- il catalogo resta autoritativo per slug, accessibilità, campi e
  disponibilità;
- le interpretazioni dell'LLM devono essere marcate come `inferred`;
- le contraddizioni devono essere conservate e segnalate;
- nessuna pagina viene pubblicata se il lint fallisce;
- le pagine obsolete non vengono cancellate automaticamente;
- ogni modifica deve avere data, fonte e motivazione.

Una wiki mantenuta da un LLM può consolidare errori se non ha vincoli e
verifiche; la provenienza dei dati e la validazione deterministica sono quindi
obbligatorie.

## 4. Query basate sulla wiki

Il runtime potrebbe:

1. cercare prima concetti e pagine semantiche;
2. seguire le relazioni verso servizi compatibili;
3. usare le sezioni `simili`, `non usare quando` e `formulazioni utente`;
4. passare al router una spiegazione strutturata e citata;
5. mostrare eventualmente all'utente perché un servizio è stato proposto.

Esempio:

```text
"voglio mettere in pausa gli studi"
        ↓
concept:study-suspension
        ↓
family:career-interruption
        ↓
service:suspension-request
        ↓
structure:student-services
```

Questo può migliorare la qualità soprattutto nei casi ambigui e nelle
richieste colloquiali, ma non automaticamente: il beneficio dipende dalla
qualità delle pagine, delle relazioni e delle fonti.

## 5. Feedback e aggiornamento

Registrare, nel rispetto della privacy, eventi come:

```text
query utente
candidati proposti
decisione finale
correzione o rifiuto dell'utente
pagina wiki coinvolta
```

L'agente potrebbe proporre modifiche, ad esempio:

> Tre utenti hanno usato “bloccare l'università” per riferirsi alla
> sospensione degli studi. Propongo di aggiungere questo alias alla pagina
> `concept:study-suspension`.

La modifica deve essere proposta e validata, non appresa automaticamente senza
controllo.

## Cosa non serve subito

Non è necessario introdurre immediatamente:

- un database a grafo o Neo4j;
- fine-tuning;
- l'uso di tutte le conversazioni come dati di training;
- la sostituzione di BM25, embeddings o RRF;
- la scrittura diretta dell'LLM in `uniticket.json`.

File Markdown versionati con Git sono sufficienti per la prima implementazione.
Il grafo può essere ricostruito dal frontmatter e dai link tra pagine.

## Ordine consigliato

1. Creare `wiki/` con pagine generate inizialmente dal catalogo.
2. Definire schema, fonti, confidence e relazioni.
3. Scrivere un importer deterministico `uniticket.json → wiki/`.
4. Aggiungere lint per pagine, link, fonti e conflitti.
5. Aggiungere un comando di aggiornamento LLM che produca diff revisionabili.
6. Compilare `wiki/ → taxonomy.json`.
7. Integrare nel retrieval le pagine wiki, mantenendo il catalogo come
   autorità operativa.
8. Aggiungere feedback e valutazione delle modifiche.
9. Valutare un database persistente solo dopo aver verificato la necessità di
   query multi-hop, aggiornamenti frequenti, storico o supporto multi-ateneo.

## Riferimento

Il pattern di riferimento è il gist di Karpathy:

<https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f>
