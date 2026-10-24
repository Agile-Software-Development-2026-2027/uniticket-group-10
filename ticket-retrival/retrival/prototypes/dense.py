import json
import logging
from pathlib import Path
from typing import Callable, List, Tuple

import numpy as np
from sentence_transformers import SentenceTransformer

from ..base import Prototype, Ticket
from .dense_callbacks import title_description_structure

logger = logging.getLogger(__name__)
OUTPUT_DIR = Path(__file__).resolve().parent / "output" / "dense"


class Dense(Prototype):
    def __init__(self, tickets: List[Ticket], device = "mps", model = "Qwen/Qwen3-Embedding-0.6B",
                 ticket_to_text: Callable[[Ticket], str] = title_description_structure, index_name: str = "default"):
        super().__init__(tickets)
        self.model = model;
        self.device = device;
        self.ticket_to_text = ticket_to_text
        self.index_name = index_name
        self.filename = OUTPUT_DIR / f"{model}_dense_{device}_{index_name}.npy"
        self.trasformer = self._model()
        self.embeddings = None
        self.ticket_ids = None
        self._prepare()

    def _embeddings(self):
        if self.embeddings is None:
            self.embeddings = np.load(self.filename)
        if self.ticket_ids is None:
            self.ticket_ids = json.loads(self.filename.with_suffix(".json").read_text(encoding="utf-8"))
        if len(self.ticket_ids) != len(self.embeddings):
            raise ValueError("Il numero di ticket non corrisponde alle righe degli embedding")
        return self.embeddings

        
    def search(self, query: str, k: int = 5) -> list[Tuple[int, float]]:
        """Ricerca usando solo la semantica (Embeddings)"""
        if k <= 0:
            return []
        query_embedding = self.trasformer.encode(query, normalize_embeddings=True)
        scores = np.dot(self._embeddings(), query_embedding)
        top_indices = np.argsort(scores)[::-1][:k]
        return [(self.ticket_ids[i], float(scores[i])) for i in top_indices]

    def _model(self) -> SentenceTransformer:
        return SentenceTransformer(self.model, device=self.device)
    
    def _exists(self) -> bool:
        return self.filename.exists() and self.filename.with_suffix(".json").exists()

    def _prepare(self) -> None:
        ids_file = self.filename.with_suffix(".json")
        if self._exists():
            self._embeddings()
            return
        if not self.tickets:
            raise ValueError("Il dataset non contiene ticket da indicizzare")
        logger.info("Non esistono embeddings per l'indice %s, modello %s su %s: li creo.", self.index_name, self.model, self.device)

        documents = [self.ticket_to_text(ticket) for ticket in self.tickets]
        document_embeddings = self.trasformer.encode_document(documents, normalize_embeddings=True)
        self.filename.parent.mkdir(parents=True, exist_ok=True)
        np.save(self.filename, document_embeddings)
        self.ticket_ids = [ticket.ticket_category_id for ticket in self.tickets]
        ids_file.write_text(json.dumps(self.ticket_ids), encoding="utf-8")
        self.embeddings = document_embeddings


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    tickets = json.loads(Path("dataset.json").read_text(encoding="utf-8"))
    titles = {ticket["ticket_category_id"]: ticket["title"] for ticket in tickets}
    dense = Dense(tickets)
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
        for ticket_id, score in dense.search(query):
            print(f"Ticket {ticket_id} - {titles.get(ticket_id, 'Titolo non disponibile')}: {score:.4f}")


if __name__ == "__main__":
    main()
