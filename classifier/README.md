# Classificatore delle richieste

Dato un messaggio in linguaggio naturale, trova il modulo giusto di [uniTicket](https://ticket.unical.it):

- **se è sicuro** propone un solo modulo, con il link;
- **se è incerto** fa una domanda e mostra i candidati migliori (si risponde a parole o con un numero);
- **se nessun modulo è adatto** lo dice.

Non compila e non invia i ticket: si ferma al link del modulo.

## Avvio

Tutti i comandi vanno lanciati da `classifier/`. Servono Java 21+, la chiave di Jev (TypeSafe AI) e [Ollama](https://ollama.com) con `bge-m3` per la ricerca semantica. Maven non serve, c'è il wrapper.

```bash
ollama pull bge-m3
export TYPESAFE_API_KEY=...
./mvnw -q package
java -jar target/uniticket-chatbot.jar                    # chat
java -jar target/uniticket-chatbot.jar --debug            # mostra ricerca, stima e decisione di ogni turno
java -jar target/uniticket-chatbot.jar eval --split dev   # valutazione
java -jar target/uniticket-chatbot.jar build-catalog      # rigenera data/catalog.json da raw_cache
```

Senza Ollama il bot usa solo la ricerca per parole chiave (`--lexical-only` lo forza). In chat, `/nuova` ricomincia e `/esci` chiude.

## Come funziona

```mermaid
flowchart TD
    U["Messaggio dell'utente"] --> R{"Risposta chiusa?<br/>'2', 'la seconda', 'sì'"}
    R -->|sì| OK["Modulo scelto"]
    R -->|no| S["1. Ricerca: BM25 + bge-m3<br/>→ 50 moduli aperti"]
    S --> M["2. Stima di Jev: probabilità di ogni modulo,<br/>'nessun modulo', 'servono informazioni'"]
    M --> V["3. Verifica della struttura"]
    V --> P{"4. DecisionPolicy:<br/>ipotesi che coprono l'80%"}
    P -->|"un modulo"| D{"Di un dipartimento<br/>non indicato?"}
    D -->|no| SEL["Modulo trovato"]
    D -->|sì| C["Chiede conferma"]
    P -->|"più ipotesi"| Q["Domanda e opzioni"]
    P -->|"solo 'nessun modulo'"| N["Nessun modulo"]
    Q --> U
    C --> U
```

**Il modello stima, il codice decide.** Jev restituisce una distribuzione di probabilità; poi una regola deterministica prende le ipotesi più probabili finché arrivano all'80%. Un solo modulo vuol dire sicurezza, più ipotesi vogliono dire che bisogna chiedere. Se lo stesso certificato esiste in due dipartimenti, le probabilità si dividono 50/50 e il bot chiede il dipartimento.

**La stima di Jev.** Jev non scrive testo: gli si fanno domande tipizzate e il codice ricompone le risposte:

```text
info_insufficienti = vago
nessun_modulo      = (1 - vago) × (1 - adatto)
modulo i           = (1 - vago) × adatto × P(i)
```

**I dipartimenti.** Più della metà dei moduli appartiene a un solo dipartimento. Un modulo di dipartimento è sicuro solo se l'utente ha nominato quella struttura (per nome, sigla o corso di studi), altrimenti il bot chiede conferma. La struttura riportata dal modello vale solo se il codice la ritrova nelle parole dell'utente.

## Il codice

`src/main/java/it/unical/uniticket/`, 21 file:

| Pacchetto | Cosa fa |
|---|---|
| `catalog` | I 241 moduli disponibili; riconosce le strutture nominate in un testo |
| `search` | Ricerca BM25 (Lucene) ed embedding `bge-m3`, fusi con RRF |
| `estimate` | Le domande a Jev e la lettura delle risposte, dietro l'interfaccia `Estimator` |
| `dialog` | `ChatBot.reply` (i passi di un turno, numerati), `ChatSession` (lo stato), `DecisionPolicy`, `UserChoice` |

`ChatBot` non ha stato: riceve a ogni messaggio la `ChatSession` dell'utente, quindi un solo bot serve tutti gli utenti.

**LangGraph non serve ancora.** Il flusso ha una sola pausa (aspettare l'utente) e lo stato è già un oggetto a parte. Converrà quando il bot compilerà i ticket su più turni: ogni passo di `ChatBot.reply` diventerebbe un nodo e `ChatSession` lo stato del grafo.

## Dati

- `data/catalog.json`: le 32 strutture e i 241 moduli con il form disponibile, generati da `raw_cache` (lo scrape di uniTicket) con `build-catalog`. Non va modificato a mano.
- `data/structures-extra.json`: l'unico file curato a mano, con nomi estesi, sigle e corsi di studio. Serve a capire che "faccio giurisprudenza" vuol dire DiScAG.

## Valutazione

`eval` misura il bot sui 252 casi di `eval/cases.json`, con la data fissata a quella dello scrape. Riporta il primo turno e un dialogo con un utente "a copione". L'errore grave è la selezione sbagliata, perché l'utente non può accorgersene.

Misure con Jev del 3/11/2026, 126 casi per split:

| | dev | test |
|---|---|---|
| Selezioni giuste / sbagliate | 60 / 0 | 58 / 1 |
| Domande con il modulo giusto / senza | 35 / 17 | 33 / 18 |
| "Nessun modulo" giusti / a torto | 14 / 0 | 12 / 4 |

I casi sono scritti da un LLM che conosceva il catalogo, quindi i numeri sono ottimistici. `eval/casi-reali.json` serve a raccogliere richieste scritte da persone: si misura con `eval --cases eval/casi-reali.json --split all`.

## Test

```bash
./mvnw test
```

87 test, nessuno chiama un modello:

- `ChatBotTest`: il dialogo con un modello finto;
- `DecisionPolicyTest`: la regola dell'80% e i dipartimenti;
- `UserChoiceTest`: le risposte chiuse;
- `CatalogTest`: il riconoscimento delle strutture;
- `JevEstimatorTest`: la lettura delle risposte di Jev.

## Prossimi passi

1. Raccogliere richieste reali e misurarle.
2. Collegarlo alla UI dell'assistente come servizio HTTP.
3. Valutare la sola ricerca semantica, senza BM25: stessa copertura a 50 candidati, ma va rimisurata.
4. Compilazione assistita dei ticket.
