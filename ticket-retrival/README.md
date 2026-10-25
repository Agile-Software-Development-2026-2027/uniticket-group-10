## Ticket retrieval

Esperimenti per individuare il form UniTicket più pertinente a una richiesta dell'utente. Include i prototipi di ricerca Embedding (di tipo Dense ad esempio Qwen), BM25 e Hybrid (Embedding+BM25 ma forse l'ho implementato male), gli strumenti per generare le query di test e un benchmark condiviso per confrontare i risultati.

## Indice

1. [Descrizione del benchmark e istruzioni per l’esecuzione](./BENCHMARK.md)
2. [Generazione delle query e descrizione del dataset](./dataset/README.md)
3. [Implementazione dei prototipi e stato attuale dello sviluppo](./prototypes/README.md)



## Ambiente Python con uv

Prima installa `uv`, se non è già disponibile:

```bash
pip install uv
```

```bash
uv sync --locked
```


### Osservazioni
#### Tipologie di ticket duplicate tra dipartimenti
Molti dipartimenti hanno la stessa tipologia di ticket, per farvi un esempio:

- Domanda di riconoscimento esami/cfu - DISPES
- Domanda di riconoscimento esami/cfu - DISCA
- Domanda di riconoscimento esami/cfu - DIMES

Questo significa che l'agente deve essere in grado di riconoscere la domanda più pertinente per raggiungere il ticket giusto. In questo csao la domanda che dovrebbe fare è "Per quale dipartimento?"

### Visibilità dei ticket in base alla tipologia di utente
Abbiamo diverse tipologie di utenti, ciascuna delle quali può visualizzare categorie di ticket differenti.

Dobbiamo assicurarci che l'agente consideri solo i ticket visibili all'utente corrente, rispettando le restrizioni di accesso (che attualmente UniTicket gestisce solo parzialmente...).

### La struttura del ticket può essere utile
Nel dump che possiedo, al momento abbiamo disponibili i seguenti campi:
```
[
  "BaseDateField",
  "CheckBoxField",
  "CustomCharField",
  "CustomComplexTableField",
  "CustomDataField",
  "CustomEmailField",
  "CustomFileField",
  "CustomHiddenField",
  "CustomImageField",
  "CustomPDFField",
  "CustomRadioBoxField",
  "CustomSelectBoxField",
  "CustomURLField",
  "MultiCheckBoxField",
  "PositiveFloatField",
  "PositiveIntegerField",
  "TextAreaField"
]
```
Analizzando questi campi, possiamo osservare che:
- Alcuni contengono valori predefiniti (default values).
- Alcuni sono obbligatori (required).
- Alcuni consentono all'utente di selezionare una o più opzioni predefinite.
- Le label dei campi possono fornire informazioni aggiuntive sul servizio offerto dal ticket.
- Alcuni campi hanno l'attributo "aiuto"

Queste informazioni potrebbero essere sfruttate per arricchire la rappresentazione delle categorie di ticket, soprattutto quando titolo e descrizione non sono sufficientemente informativi.

## Utilizzo di un LLM per arricchire le informazioni
A partire da queste informazioni, l'LLM potrebbe generare:

Query correlate: richieste realistiche che un utente potrebbe formulare per accedere a quel servizio, anche utilizzando termini diversi da quelli presenti nel titolo o nella descrizione.

Descrizioni arricchite: testi che descrivono in maniera più completa le operazioni consentite dal form, i possibili casi d'uso e il contesto del servizio.

Le descrizioni generate potrebbero successivamente essere utilizzate per migliorare l'indicizzazione BM25 o la generazione degli embeddings.

#### Esempi concreti

**Esempio 1 — Dipartimenti**

Label: `Dipartimento`

Opzioni:
- Dipartimento di Economia, Statistica e Finanza "Giovanni Anania" (DESF)
- Dipartimento di Scienze Aziendali e Giuridiche (DiSCAG)
- Dipartimento di Scienze Politiche e Sociali (DISPES)

**Informazione ricavabile:** il ticket può essere utilizzato nel contesto di più dipartimenti.

**Esempio 2 — Prova finale di un Master**

Label: `Per quale Master vuole sostenere la prova finale?`

Opzioni:
- Master in "Management delle Amministrazioni Pubbliche"
- Master in "Diritto del lavoro, welfare e servizi per l'impiego"
- Master in "Management del Turismo e del Turismo Residenziale"

**Informazione ricavabile:** il ticket riguarda la prova finale di specifici Master.

Questa informazione è particolarmente utile per generare query più realistiche e contestualizzate, ad esempio:

- "Devo sostenere la prova finale del Master in Management delle Amministrazioni Pubbliche."
- "Come posso richiedere la prova finale del Master in Diritto del lavoro?"

Le stesse informazioni potrebbero essere incluse nel testo utilizzato per generare gli embeddings.

**Esempio 3 — Tipologie di richieste di acquisto**

Label: `La richiesta può essere classificata come (scegliere un'opzione)`

Opzioni:
- Acquisizione di materiale di consumo generico (cancelleria, cartucce toner, materiale igienico-sanitario, ecc.) o realizzazione di lavori di interesse generale del dipartimento.
- Acquisizione di beni/servizi di natura informatica o realizzazione di reti dati.
- Acquisizione di beni/servizi di natura tecnica o realizzazione di impianti tecnologici.
- Acquisizione di strumentazione o beni/servizi di natura scientifica.

**Informazione ricavabile:** il form permette di classificare richieste relative a diverse tipologie di acquisti, servizi e lavori.

### Attributo "aiuto"
"aiuto": "Attenzione: la presente domanda è valida esclusivamente per la partecipazione al Programma DUnicAL CAREER e non costituisce domanda di ammissione o iscrizione ai corsi di studio, per i quali restano valide le procedure e le scadenze previste nei bandi",
