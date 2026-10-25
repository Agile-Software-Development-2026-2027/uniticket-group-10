# Prototipi

L'obiettivo è avere un'interfaccia condivisa, `Prototype` in `base.py`, per poter
eseguire gli stessi benchmark sui vari prototipi.

**Nota bene:** non è ancora stato fatto praticamente nulla, quindi se stai leggendo questo e vuoi lavorare ai prototipi, sentiti libero di farlo.

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
