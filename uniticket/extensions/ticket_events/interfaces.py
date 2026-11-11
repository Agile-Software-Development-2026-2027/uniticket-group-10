"""Contratti di integrazione per gli eventi delle definizioni TicketCategory."""

from typing import Literal, Protocol, TypeAlias

from .index_fields import CategoryMetadata


# I valori identificano il CRUD della categoria, indipendentemente dal trasporto.
CategoryOperation: TypeAlias = Literal["CREATE", "UPDATE", "DELETE"]


class EmbeddingProvider(Protocol):
    """Contratto del componente che converte il testo in un vettore."""

    # Descrive la chiamata che genera il vettore di una categoria.
    def embed(self, text: str) -> list[float]:
        """Converte il testo costruito da nome e descrizione della categoria."""
        ...

    # Descrive la chiamata che genera il vettore di una ricerca.
    def embed_query(self, text: str) -> list[float]:
        """Converte il testo della query in un vettore."""
        ...


class IndexRepository(Protocol):
    """Contratto del componente che gestisce i record dell’indice vettoriale."""

    # Descrive l’inserimento o la sostituzione del record completo.
    def upsert(
        self,
        category_id: int,
        vector: list[float],
        metadata: CategoryMetadata,
    ) -> None:
        """Inserisce o sostituisce il record della categoria con vettore e metadata."""
        ...

    # Descrive la rimozione del record tramite ID categoria.
    def delete(self, category_id: int) -> None:
        """Rimuove il record della categoria, accettando anche un ID già assente."""
        ...

    # Descrive la ricerca limitata alle categorie autorizzate dall'applicazione.
    def search(
        self,
        vector: list[float],
        top_k: int,
        authorized_category_ids: list[int],
    ) -> list[int]:
        """Restituisce gli ID dei punti più vicini, in ordine di similarità."""
        ...


class IndexNotifier(Protocol):
    """Indica quali argomenti deve accettare la chiamata fatta da notify_index()."""

    # Richiede due argomenti: CREATE/UPDATE/DELETE e ID della categoria.
    def __call__(self, operation: CategoryOperation, category_id: int) -> None:
        """Riceve operazione e ID dopo il commit della transazione Django."""
        ...
