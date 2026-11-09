"""Real Django receivers for the agreed TicketCategory embedding inputs.

CREATE e UPDATE notificano il destinatario configurato dopo il commit.
DELETE conserva il log dimostrativo fino al successivo incremento.
"""
import json
import logging
from functools import partial
from django.db import transaction
from django.db.models.signals import pre_save, post_save, pre_delete, post_delete
from django.dispatch import receiver
from .content import snapshot, office_snapshots
from .notifications import safe_notify

logger = logging.getLogger("ticket_events")
CATEGORY = "uni_ticket.TicketCategory"
OFFICE = "organizational_area.OrganizationalStructureOffice"
STATE = "_ticket_events_before"


def handle_definition_event(event):
    """Riceve l'evento confermato e lo mostra: nessuna azione sugli embedding."""
    logger.info("[TICKET EVENT] %s", json.dumps(event, ensure_ascii=False, indent=2))

    # PUNTO DI ESTENSIONE FUTURO (non implementato e non eseguito):
    # - INDEX: inviare category_id e il testo costruito da after alla pipeline di indicizzazione.
    # - REINDEX: richiedere la sostituzione dei vettori della tipologia.
    # - NONE: nessuna richiesta alla pipeline.
    # - REMOVE: richiedere la rimozione dei vettori associati a category_id.
    # Prima serviranno coda persistente, retry e operazioni idempotenti.
    # Oggi questa funzione scrive ESCLUSIVAMENTE il messaggio nel terminale.
def report(signal, sender, source_id, category_id, before, after, using):
    if before is None and after is None:
        return
    if before is None:
        operation, action = "CREATED", "INDEX"
    elif after is None:
        operation, action = "DELETED", "REMOVE"
    elif before == after:
        operation, action = "UNCHANGED", "NONE"
    else:
        operation, action = "UPDATED", "REINDEX"
    event = {
        "signal": signal,
        "source_model": sender._meta.label,
        "category_id": category_id,
        "operation": operation,
        "possible_action": action,
        "before": before,
        "after": after,
    }
    # Called after successful commit, or immediately when outside a transaction.
    transaction.on_commit(
        lambda: handle_definition_event(event),
        using=using,
    )

@receiver(pre_save, sender=CATEGORY, dispatch_uid="ticket_events.category_before")
def category_before(sender, instance, using, raw=False, **kwargs):
    if not raw:
        setattr(instance, STATE, snapshot(instance.pk, using) if instance.pk else None)

@receiver(post_save, sender=CATEGORY, dispatch_uid="ticket_events.category_saved")
def category_saved(sender, instance, created, using, raw=False, **kwargs):
    if raw:  # Durante loaddata i dati correlati possono essere ancora incompleti.
        return
    if created:
        if hasattr(instance, STATE):
            delattr(instance, STATE)
        # partial conserva l’ID attuale anche se l’istanza cambia prima del commit.
        callback = partial(safe_notify, "CREATE", instance.pk)
        transaction.on_commit(callback, using=using)
        return
    # L’istanza può contenere modifiche escluse da update_fields: conta il database.
    before = getattr(instance, STATE, None)
    if hasattr(instance, STATE):
        delattr(instance, STATE)
    if before is None:
        logger.warning("Stato precedente assente: category_id=%s", instance.pk)
        return
    after = snapshot(instance.pk, using)
    if after is not None and before != after:
        callback = partial(safe_notify, "UPDATE", instance.pk)
        transaction.on_commit(callback, using=using)

@receiver(pre_delete, sender=CATEGORY, dispatch_uid="ticket_events.category_deleting")
def category_deleting(sender, instance, using, **kwargs):
    setattr(instance, STATE, snapshot(instance.pk, using))

@receiver(post_delete, sender=CATEGORY, dispatch_uid="ticket_events.category_deleted")
def category_deleted(sender, instance, using, **kwargs):
    before = getattr(instance, STATE, None)
    if hasattr(instance, STATE):
        delattr(instance, STATE)
    report("post_delete", sender, instance.pk, instance.pk, before, None, using)

@receiver(pre_delete, sender=OFFICE, dispatch_uid="ticket_events.office_deleting")
def office_deleting(sender, instance, using, **kwargs):
    # SET_NULL aggiorna i metadata senza chiamare TicketCategory.save().
    setattr(instance, STATE, office_snapshots(instance.pk, using))

@receiver(post_delete, sender=OFFICE, dispatch_uid="ticket_events.office_deleted")
def office_deleted(sender, instance, using, **kwargs):
    before = getattr(instance, STATE, {})
    if hasattr(instance, STATE):
        delattr(instance, STATE)
    for category_id, previous_state in before.items():
        current_state = snapshot(category_id, using)
        # Le categorie rimaste ricevono UPDATE perché è cambiato l’ID dell’ufficio.
        if current_state is not None and previous_state != current_state:
            callback = partial(safe_notify, "UPDATE", category_id)
            transaction.on_commit(callback, using=using)
