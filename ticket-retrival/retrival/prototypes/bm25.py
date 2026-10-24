import json
import re
from pathlib import Path
from typing import List, Tuple

from rank_bm25 import BM25Okapi

from ..base import Prototype, Ticket


class BM25(Prototype):
    """Ricerca lessicale sui ticket, senza modelli o embedding."""

    def __init__(self, tickets: List[Ticket], k1=1.5, b=0.75, epsilon=0.25):
        # tickets: categorie da indicizzare, con ID, titolo, descrizione e struttura.
        # k1: regola quanto contano le ripetizioni di una parola nel documento;
        # valori più alti fanno saturare più lentamente il loro contributo.
        # b: corregge il punteggio in base alla lunghezza del documento;
        # 0 disattiva la correzione, 1 applica la correzione completa.
        # epsilon: moltiplicatore dell'IDF medio usato da BM25Okapi per
        # sostituire gli IDF negativi dei termini presenti in oltre metà corpus.
        super().__init__(tickets)
        self.ticket_ids = []
        corpus = []
        for ticket in self.tickets:
            text = " ".join((
                ticket.title or "",
                ticket.description or "",
                ticket.structure.get("name") or "",
            ))
            corpus.append(self._tokenize(text))
            self.ticket_ids.append(ticket.ticket_category_id)

        self._positions = {ticket_id: i for i, ticket_id in enumerate(self.ticket_ids)}
        self.index = (
            BM25Okapi(corpus, k1=k1, b=b, epsilon=epsilon)
            if any(corpus) else None
        )

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return re.findall(r"\b\w+\b", text.lower())

    def search(self, query: str, k: int = 5) -> list[Tuple[int, float]]:
        """Restituisce gli ID dei primi k ticket e i punteggi divisi per il massimo positivo."""
        return self.search_within(query, self.ticket_ids, k)

    def search_within(self, query: str, ticket_ids, k: int = 5) -> list[Tuple[int, float]]:
        """Valuta solo i candidati, usando le statistiche dell'intero catalogo."""
        if k <= 0 or self.index is None:
            return []
        candidate_ids = list(dict.fromkeys(ticket_ids))
        if not candidate_ids:
            return []
        try:
            positions = [self._positions[ticket_id] for ticket_id in candidate_ids]
        except KeyError as exc:
            raise ValueError(f"Ticket non presente nell'indice BM25: {exc.args[0]}") from exc
        tokens = self._tokenize(query)
        if not any(token in self.index.idf for token in tokens):
            return []

        scores = self.index.get_batch_scores(tokens, positions)
        # Normalizza sui soli candidati; eventuali valori negativi restano negativi.
        max_bm25 = max(scores)
        if max_bm25 > 0:
            scores = [score / max_bm25 for score in scores]
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
        return [(candidate_ids[i], float(scores[i])) for i in top_indices]


def main():
    tickets = json.loads(Path("dataset.json").read_text(encoding="utf-8"))
    bm25 = BM25(tickets)
    titles = {ticket.ticket_category_id: ticket.title for ticket in bm25.tickets}
    while True:
        try:
            query = input("\nDescrivi la richiesta (exit per uscire): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if query.lower() == "exit":
            break
        if not query:
            continue
        results = bm25.search(query)
        if not results:
            print("Nessun ticket trovato.")
        for ticket_id, score in results:
            print(f"Ticket {ticket_id} - {titles[ticket_id]}: {score:.4f}")


if __name__ == "__main__":
    main()
