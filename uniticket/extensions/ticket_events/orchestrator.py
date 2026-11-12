"""Registra l'azione CRUD prevista senza modificare l'indice."""
import logging

from .interfaces import CategoryOperation

logger = logging.getLogger("ticket_events.orchestrator")


# Associa CREATE a INDEX, UPDATE a REINDEX e DELETE a REMOVE.
def synchronize(operation: CategoryOperation, category_id: int) -> None:
    if operation == "CREATE":
        # Pseudocodice quando sarà disponibile l'embedder:
        # category = snapshot(category_id, using="default")
        # text = embedding_text(category)
        # vector = embedder.embed(text)
        # metadata = category_metadata(category)
        # repository.upsert(category_id, vector, metadata)
        action = "INDEX"
    elif operation == "UPDATE":
        # Pseudocodice: ricalcolare il vettore e sostituire il punto esistente.
        # category = snapshot(category_id, using="default")
        # text = embedding_text(category)
        # vector = embedder.embed(text)
        # metadata = category_metadata(category)
        # repository.upsert(category_id, vector, metadata)
        action = "REINDEX"
    elif operation == CategoryOperation.DELETE:
        action = "REMOVE"
        # Pseudocodice: rimuovere dal repository il punto identificato dall'ID.
        # repository.delete(category_id)
    else:
        raise ValueError(f"Operazione sconosciuta: {operation}")

    # Stampa operazione, ID e azione scelta; per ora non aggiorna alcun vettore.
    logger.info(
        "[ORCHESTRATION] operation=%s category_id=%s action=%s",
        operation, category_id, action,
    )
