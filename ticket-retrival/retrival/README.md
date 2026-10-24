# Prototipi

L'obiettivo è avere un'interfaccia condivisa, `Prototype` in `base.py`, per poter
eseguire gli stessi benchmark sui vari prototipi.

## Interfaccia condivisa

```python
def search(self, query: str, k: int = 5) -> List[Tuple[int, float]]:
    ...
```

Restituisce, per una query, al massimo `k` coppie `(ticket_category_id, score)`,
ordinate per pertinenza decrescente. Il punteggio non è una probabilità di
correttezza. Ogni nuovo prototipo deve rispettare questa interfaccia.

```python
def __init__(self, tickets: List[Ticket]):
    ...
```

Il costruttore di `Prototype` salva i ticket in `self.tickets`. I prototipi usano questi dati per
preparare i propri indici: ad esempio, Dense genera gli embedding e BM25
costruisce un indice lessicale.

## Quali prototipi sono stati implementati?

| Prototipo | Come cerca | Parametri principali |
| --- | --- | --- |
| `Dense` | Similarità semantica tramite embedding | `model`, `device`, `ticket_to_text`, `index_name` |
| `BM25` | Corrispondenze tra parole di query e ticket, con maggiore peso ai termini rari. | `k1`, `b`, `epsilon` |
| `Hybrid` | Dense recupera i candidati, BM25 contribuisce a riordinarli. `alpha` rappresenta il peso di Dense; BM25 pesa `1 - alpha`. | `alpha`, `candidate_k` |

TODO: provare jev e combinarlo con gli altri approcci.

## Come funziona Dense?

Dense usa per default `Qwen/Qwen3-Embedding-0.6B` su
`mps`; il primo caricamento può richiedere il download del modello.

Funziona in due fasi: preparazione dell'indice e ricerca. Il benchmark valuta poi
la qualità dei risultati sulle query di test.

### Cos'è un embedding?

Un embedding è una rappresentazione numerica di un testo sotto forma di vettore, generata da un modello di machine learning. Questo vettore cerca di catturare il significato semantico del testo, permettendo di confrontare testi anche quando utilizzano parole diverse.

Testi con significati simili tendono ad avere embedding vicini nello spazio vettoriale. La loro somiglianza può essere misurata, ad esempio, attraverso la cosine similarity.

Gli embedding vengono salvati dentro `retrival/prototypes/output/dense/`,
indipendentemente dalla cartella di avvio. Per ogni configurazione vengono
prodotti un file `.npy` e un file `.json` degli ID.

Il file degli embedding (.npy) contiene una matrice: ogni riga rappresenta un ticket. Il file degli ID (.json) contiene gli ID delle categorie nello stesso ordine: l’elemento in posizione i identifica la categoria associata alla riga i della matrice.

### Approccio

Di default, per ogni categoria di ticket vengono concatenati titolo, descrizione e struttura organizzativa in un unico testo, tramite una funzione (callback). Il modello genera un embedding a partire dal testo restituito.

### Voglio generare gli embedding su un testo diverso

Puoi passare una callback personalizzata a Dense. Le callback sono raccolte in
`prototypes/dense_callbacks.py`.

La callback è definita come `def ticket_to_text(ticket: Ticket) -> str:`. Puoi sfruttare l'oggetto Ticket per provare a costruire diverse callback.

### Un esempio rapido

```python
import json
from pathlib import Path

from retrival.base import Ticket
from retrival.prototypes.dense import Dense

records = json.loads(Path("dataset.json").read_text(encoding="utf-8"))
tickets = [Ticket.from_dict(record) for record in records]

# Definiamo una callback.
def ticket_to_text(ticket: Ticket) -> str:
    text = f"Titolo: {ticket.title}\nDescrizione: {ticket.description or ''}"
    labels = ", ".join(field.name for field in ticket.fields)
    return f"{text}\nCampi del modulo: {labels}"

# Prepariamo il prototipo Dense.
dense = Dense(
    tickets,
    device="cpu",
    ticket_to_text=ticket_to_text,
    index_name="esperimento_con_campi_del_modulo_v1",
)

dense.search("Come richiedo una borsa di studio?", k=5)
```

Il costruttore di Dense carica la cache se esiste; altrimenti esegue la callback
e genera gli embedding. La callback trasforma i ticket, non le query degli utenti.

La cache dipende da modello, device e `index_name`. Quando cambi dataset o
callback, cambia anche `index_name`: riutilizzare il nome precedente carica la
vecchia cache senza rilevare le modifiche. Le cache degli altri esperimenti
restano su disco.

## Avvio interattivo

Eseguire i comandi dalla cartella **`ticket-retrival`**, che contiene
`dataset.json` e il pacchetto `retrival`:

```bash
uv run python -m retrival.prototypes.bm25
uv run python -m retrival.prototypes.dense
```

Ogni comando avvia un ciclo che legge una richiesta e stampa dettagli e
punteggio dei primi cinque risultati. Per uscire: `exit`, Ctrl+C o fine input.
Usare `-m` per mantenere corretti gli import relativi.

## BM25

BM25 indicizza titolo, descrizione e struttura, dividendo il testo in parole
minuscole. `k1=1.5` regola la saturazione delle ripetizioni,
`b=0.75` la correzione per lunghezza ed `epsilon=0.25` il trattamento degli IDF
negativi di `BM25Okapi`.

### Parametro k1

Più volte compare una parola, meno contribuisce ogni ripetizione aggiuntiva.

- k1 piccolo: il contributo si satura rapidamente.
- k1 grande: le ripetizioni hanno un peso maggiore.
- `k1 = 1.5`: valore predefinito del prototipo.

### Parametro b

Un documento molto lungo ha naturalmente più possibilità di contenere le parole della query.

Supponiamo di avere:

- Ticket A: descrizione di 20 parole, in cui "certificato" compare 2 volte.
- Ticket B: descrizione di 500 parole, in cui "certificato" compare 2 volte.

A parità delle altre condizioni, BM25 tende a dare maggiore importanza al Ticket A, perché la parola cercata è più concentrata nel testo.

Il parametro b controlla quanto penalizzare i documenti lunghi.

- Valori bassi (vicini a 0): la lunghezza del documento influisce poco sul punteggio.
- Valori alti (vicini a 1): la lunghezza influisce maggiormente, penalizzando i documenti più lunghi rispetto alla lunghezza media.
- `b = 0.75`: valore predefinito del prototipo.

### Parametro epsilon

Il parametro epsilon serve a gestire le parole troppo comuni, cioè quelle che compaiono in moltissimi documenti.
Esempio ipotetico con UniTicket: supponiamo di avere 547 categorie di ticket:

- "richiesta" compare in 500 categorie.
- "certificato" compare in 40 categorie.
- "pergamena" compare in 5 categorie.

BM25 utilizza l'IDF per dare più importanza alle parole rare, perché aiutano a distinguere i documenti.

Nell'implementazione BM25Okapi, però, le parole presenti in più della metà dei documenti ricevono un IDF negativo.

Questo potrebbe comportare che un documento perda punti perché contiene una parola della query molto comune.

| Valore | Effetto sui termini con IDF negativo |
| --- | --- |
| `epsilon = 0` | Non contribuiscono al punteggio. |
| `epsilon = 0.25` | L'IDF viene sostituito con il 25% dell'IDF medio. |
| `epsilon = 1` | L'IDF viene sostituito con l'intero IDF medio. |

L'IDF medio non è necessariamente positivo: questa sostituzione non garantisce
che tutti i punteggi siano positivi.

## Ricerca ibrida

```python
from retrival.prototypes.bm25 import BM25

bm25 = BM25(tickets)
query = "borsa di studio"
results = dense.search(query, k=15)
ticket_ids = [ticket_id for ticket_id, _ in results]
subset = bm25.search_within(query, ticket_ids, k=5)
```

`search_within` valuta solo gli ID indicati, che devono esistere nell'indice,
mantenendo le statistiche dell'intero catalogo. I punteggi sono divisi per il
massimo positivo dei candidati: eventuali valori negativi restano negativi.

Questo esempio seleziona i candidati con Dense e li riordina con BM25. Per
combinare anche i punteggi dei due motori, usare `Hybrid`:

```python
from retrival.prototypes.bm25 import BM25
from retrival.prototypes.hybrid import Hybrid

hybrid = Hybrid(tickets, alpha=0.7, candidate_k=15)
results = hybrid.search(query, k=5)
```

Hybrid costruisce internamente Dense e BM25 sullo stesso catalogo. Per configurarli
puoi passare `dense_kwargs` e `bm25_kwargs`, anche tramite la CLI:

```bash
uv run python benchmark.py --prototype retrival/prototypes/hybrid.py \
  --alpha 0.7 --candidate-k 15 \
  --dense-kwargs '{"device":"cpu"}' --bm25-kwargs '{"k1":1.2}'
```

Hybrid recupera
`max(k, candidate_k)` risultati da Dense e chiama
`BM25.search_within()` solo su questi. La fusione usa:

```text
score = alpha * dense_score + (1 - alpha) * bm25_score
```

Con `alpha=0.7` i pesi sono 70% Dense e 30% BM25. Anche con `alpha=0` i risultati
restano limitati ai candidati di Dense. Aumentare `candidate_k` permette a BM25 di
considerare più ticket; non può recuperare quelli esclusi da Dense.

Per confrontare configurazioni, usare le stesse query di valutazione e variare
testo dei documenti, modello, parametri BM25, `alpha` o `candidate_k`. Gli esempi
aggiunti ai documenti devono essere separati dalle query usate per valutare.
