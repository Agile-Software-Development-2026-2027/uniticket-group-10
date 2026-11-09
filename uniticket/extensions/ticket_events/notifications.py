"""Confine di notifica dell’indicizzazione, sostituibile tramite impostazioni."""

import json
import logging

from django.conf import settings
from django.utils.module_loading import import_string

from .interfaces import CategoryOperation, IndexNotifier


logger = logging.getLogger("ticket_events")


def log_notification(operation: CategoryOperation, category_id: int, *, event=None) -> None:
    """Mostra il signal ricevuto e i dati rilevanti, senza elaborare embedding."""
    if event is None:
        event = {
            "signal": "post_delete" if operation == "DELETE" else "post_save",
            "source_model": "TicketCategory",
            "category_id": category_id,
            "operation": operation,
            "possible_action": {"CREATE": "INDEX", "UPDATE": "REINDEX", "DELETE": "REMOVE"}[operation],
        }
    logger.info("[TICKET EVENT] %s", json.dumps(event, ensure_ascii=False, indent=2))


def notify_index(operation: CategoryOperation, category_id: int, *, event=None) -> None:
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
    if notifier is log_notification:
        # I dettagli sono soltanto diagnostici: il contratto esterno resta operazione + ID.
        notifier(operation, category_id, event=event)
    else:
        notifier(operation, category_id)


def safe_notify(operation: CategoryOperation, category_id: int, *, event=None) -> None:
    """Registra un fallimento esterno dopo il commit, preservando il CRUD riuscito."""
    try:
        notify_index(operation, category_id, event=event)
    except Exception:
        # Il commit è già avvenuto: il log conserva contesto e stack trace per la diagnosi.
        logger.exception(
            "Index notification failed: operation=%s, category_id=%s",
            operation,
            category_id,
        )
