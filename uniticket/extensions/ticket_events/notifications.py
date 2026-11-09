"""Confine di notifica dell’indicizzazione, sostituibile tramite impostazioni."""

import json
import logging

from django.conf import settings
from django.utils.module_loading import import_string

from .interfaces import CategoryOperation, IndexNotifier


logger = logging.getLogger("ticket_events")


def log_notification(operation: CategoryOperation, category_id: int) -> None:
    """Destinatario fittizio predefinito del laboratorio locale."""
    event = {
        "operation": operation,
        "category_id": category_id,
        "delivery": "demo",
    }
    logger.info("[TICKET EVENT] %s", json.dumps(event, indent=2))


def notify_index(operation: CategoryOperation, category_id: int) -> None:
    """Inoltra operazione e ID al destinatario concordato con l’indicizzatore."""
    notifier: IndexNotifier | str = getattr(
        settings, "TICKET_EVENTS_NOTIFIER", log_notification,
    )
    # Un percorso Python permette di configurare il destinatario senza importarlo nei receiver.
    if isinstance(notifier, str):
        notifier = import_string(notifier)
    # Il contratto invocabile accetta sia funzioni sia oggetti come FakeNotifier.
    if not callable(notifier):
        raise TypeError("TICKET_EVENTS_NOTIFIER deve essere un destinatario invocabile")
    notifier(operation, category_id)


def safe_notify(operation: CategoryOperation, category_id: int) -> None:
    """Registra un fallimento esterno dopo il commit, preservando il CRUD riuscito."""
    try:
        notify_index(operation, category_id)
    except Exception:
        # Il commit è già avvenuto: il log conserva contesto e stack trace per la diagnosi.
        logger.exception(
            "Index notification failed: operation=%s, category_id=%s",
            operation,
            category_id,
        )
