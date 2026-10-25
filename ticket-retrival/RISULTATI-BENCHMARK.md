# Risultati Benchmark — UniTicket

**Ultimo aggiornamento:** 25 ottobre 2026

## Dataset di valutazione — A0

| Parametro | Valore |
|---|---|
| Categorie nel catalogo | 229 |
| Categorie rappresentate nella valutazione | 186 |
| Categorie senza richieste di valutazione | 43 |
| Richieste totali | 1.674 |
| Richieste `direct` | 558 |
| Richieste `paraphrase` | 558 |
| Richieste `indirect` | 558 |
| Etichette corrette per richiesta | 1 |
| Risultati recuperati per richiesta (K) | 10 |
| Ground Truth validata semanticamente | No |
| Separazione sviluppo/test | No |
| SHA-256 catalogo | `5185fa8cb53baf7d805ff430f223461b891900207ab935c519df673923031959` |
| SHA-256 dataset | `1b3dc8e4bd665420b96322f879bcd0846eaa266787a8d924806aeeca145e2587` |

## Risultati complessivi — A0

| Run | Prototipo | Implementazione | Benchmark | N | Top-1 Accuracy | Recall@5 | Recall@10 | MRR@5 | Media (ms) | Mediana (ms) | P95 (ms) | Errori tecnici | Astensioni |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A0-BM25-01 | BM25 | `retrival/prototypes/bm25.py` | Originale | 1.674 | 44,21%* | 65,29%* | 73,48%* | 0,523497 | N/D | N/D | N/D | N/D | N/D |
| A0-BM25-02 | BM25 | `retrival/prototypes/bm25.py` | Esteso | 1.674 | 44,21% | 65,29% | 73,48% | 0,523497 | 1,0902 | 1,0142 | 1,8204 | 0 | 0 |

*Valori corrispondenti agli Hit@K registrati dal benchmark originale. N/D = non rilevato.*

## Risultati per tipo di richiesta — A0-BM25-02

| Tipo di richiesta | N | Top-1 Accuracy | Recall@5 | Recall@10 | MRR@5 | Media (ms) | P95 (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|
| `direct` | 558 | 61,83% | 84,77% | 89,43% | 0,711141 | 0,8908 | 1,4807 |
| `paraphrase` | 558 | 37,99% | 56,81% | 67,56% | 0,452001 | 1,0213 | 1,6126 |
| `indirect` | 558 | 32,80% | 54,30% | 63,44% | 0,407348 | 1,3586 | 2,0903 |

