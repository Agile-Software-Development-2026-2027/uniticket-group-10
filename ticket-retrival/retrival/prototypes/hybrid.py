from ..base import Prototype
from .dense import Dense
from .bm25 import BM25

class Hybrid(Prototype):

    def __init__(self, tickets, alpha=0.7, candidate_k=15, dense_kwargs=None, bm25_kwargs=None):
        # alpha pesa Dense nella fusione; BM25 pesa 1 - alpha.
        # Con 0.7: 70% Dense e 30% BM25; con 0 solo BM25, con 1 solo Dense,
        # sempre limitando i risultati ai candidati recuperati da Dense.
        # Dense recupera candidate_k ticket; la fusione ne restituisce k.
        if not 0 <= alpha <= 1:
            raise ValueError("alpha deve essere compreso tra 0 e 1")
        if candidate_k <= 0:
            raise ValueError("candidate_k deve essere positivo")
        super().__init__(tickets)
        self.dense = Dense(self.tickets, **(dense_kwargs or {}))
        self.bm25 = BM25(self.tickets, **(bm25_kwargs or {}))
        self.alpha = alpha
        self.candidate_k = candidate_k

    def search(self, query: str, k: int = 5) -> list[tuple[int, float]]:
        if k <= 0:
            return []
        dense_results = self.dense.search(query, max(k, self.candidate_k))
        if not dense_results:
            return []
        candidate_ids = [ticket_id for ticket_id, _ in dense_results]
        bm25_scores = dict(self.bm25.search_within(query, candidate_ids, len(candidate_ids)))
        results = [
            (ticket_id, self.alpha * score + (1 - self.alpha) * bm25_scores.get(ticket_id, 0.0))
            for ticket_id, score in dense_results
        ]
        return sorted(results, key=lambda item: item[1], reverse=True)[:k]
        
