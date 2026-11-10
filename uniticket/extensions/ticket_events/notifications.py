"""Chiamata all’orchestratore e registrazione degli errori."""
import logging

from .interfaces import CategoryOperation
from .orchestrator import synchronize

logger = logging.getLogger("ticket_events")


# Chiama synchronize() con CREATE, UPDATE o DELETE e l’ID della categoria.
def notify_index(operation: CategoryOperation, category_id: int) -> None:
    synchronize(operation, category_id)


# Chiama notify_index() e scrive nei log eventuali errori.
def safe_notify(operation: CategoryOperation, category_id: int) -> None:
    try:
        notify_index(operation, category_id)
    except Exception:
        # Mostra l’errore e la categoria coinvolta; non riprova la chiamata.
        logger.exception(
            "Index notification failed: operation=%s, category_id=%s",
            operation,
            category_id,
        )
