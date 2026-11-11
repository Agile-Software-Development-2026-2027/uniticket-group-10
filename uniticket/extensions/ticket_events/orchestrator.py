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
    elif operation == "DELETE":
        # Pseudocodice: rimuovere dal repository il punto identificato dall'ID.
        # repository.delete(category_id)
        action = "REMOVE"
    else:
        raise ValueError(f"Operazione sconosciuta: {operation}")

    # L'azione è soltanto diagnostica: nessun punto viene creato o rimosso.
    logger.info(
        "[ORCHESTRATION] operation=%s category_id=%s action=%s",
        operation, category_id, action,
    )
