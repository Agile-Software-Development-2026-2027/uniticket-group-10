"""Chiamata all’orchestratore e registrazione degli errori."""
import logging

from .interfaces import CategoryOperation
from .orchestrator import synchronize

logger = logging.getLogger("ticket_events")


# Chiama synchronize() e registra eventuali errori dopo il commit.
def safe_notify(operation: CategoryOperation, category_id: int) -> None:
    try:
        synchronize(operation, category_id)
    except Exception:
        # Mostra l’errore e la categoria coinvolta; non riprova la chiamata.
        logger.exception(
            "Index notification failed: operation=%s, category_id=%s",
            operation,
            category_id,
        )
