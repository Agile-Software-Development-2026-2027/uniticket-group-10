"""Primo passo dell’orchestrazione: sceglie l’azione"""
import logging

from .interfaces import CategoryOperation

logger = logging.getLogger("ticket_events.orchestrator")


# Associa CREATE a INDEX, UPDATE a REINDEX e DELETE a REMOVE.
def synchronize(operation: CategoryOperation, category_id: int) -> None:
    if operation == "CREATE":
        action = "INDEX"
    elif operation == "UPDATE":
        action = "REINDEX"
    elif operation == "DELETE":
        action = "REMOVE"
    else:
        raise ValueError(f"Operazione sconosciuta: {operation}")

    # Stampa operazione, ID e azione scelta; per ora non aggiorna alcun vettore.
    logger.info(
        "[ORCHESTRATION] operation=%s category_id=%s action=%s",
        operation, category_id, action,
    )
