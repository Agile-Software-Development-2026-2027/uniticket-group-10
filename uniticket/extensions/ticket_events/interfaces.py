"""Contratti di integrazione per gli eventi delle definizioni TicketCategory."""

from typing import Protocol, TypeAlias, Literal


# I valori identificano il CRUD della categoria, indipendentemente dal trasporto.
CategoryOperation: TypeAlias = Literal["CREATE", "UPDATE", "DELETE"]


class EmbeddingProvider(Protocol):
    """Contratto del componente che converte il testo in un vettore."""

    def embed(self, text: str) -> list[float]:
        """Converte il testo costruito da nome e descrizione della categoria."""
        ...


class IndexRepository(Protocol):
    """Contratto del componente che gestisce i record dell’indice vettoriale."""

    def upsert(
        self,
        category_id: int,
        vector: list[float],
        metadata: dict[str, object],
    ) -> None:
        """Inserisce o sostituisce il record della categoria con vettore e metadata."""
        ...

    def delete(self, category_id: int) -> None:
        """Rimuove il record della categoria, accettando anche un ID già assente."""
        ...


class IndexNotifier(Protocol):
    """Contratto invocabile dal futuro collegamento dei receiver all’indicizzatore."""

    # __call__ permette di usare una funzione notify_index o un oggetto FakeNotifier.
    def __call__(self, operation: CategoryOperation, category_id: int) -> None:
        """Riceve operazione e ID dopo il commit della transazione Django."""
        ...
