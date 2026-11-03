"""Real Django receivers for the agreed TicketCategory embedding inputs.

They read real models and emit local logs after commit; no embedding service
or vector database is called. Demo APIs are not imported by this module.
"""
import json
import logging
from django.db import transaction
from django.db.models.signals import pre_save, post_save, pre_delete, post_delete
from django.dispatch import receiver
from .content import snapshot, related_snapshots

logger = logging.getLogger("ticket_events")
CATEGORY = "uni_ticket.TicketCategory"
STRUCTURE = "organizational_area.OrganizationalStructure"
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
def category_saved(sender, instance, using, raw=False, **kwargs):
    if raw:  # Fixture synchronization must happen after the complete import.
        return
    if not hasattr(instance, STATE):
        logger.warning("[TICKET EVENT] Snapshot unavailable for category %s", instance.pk)
        return
    before = getattr(instance, STATE)
    delattr(instance, STATE)
    report("post_save", sender, instance.pk, instance.pk,
           before, snapshot(instance.pk, using), using)

@receiver(pre_delete, sender=CATEGORY, dispatch_uid="ticket_events.category_deleting")
def category_deleting(sender, instance, using, **kwargs):
    setattr(instance, STATE, snapshot(instance.pk, using))

@receiver(post_delete, sender=CATEGORY, dispatch_uid="ticket_events.category_deleted")
def category_deleted(sender, instance, using, **kwargs):
    before = getattr(instance, STATE, None)
    if hasattr(instance, STATE):
        delattr(instance, STATE)
    report("post_delete", sender, instance.pk, instance.pk, before, None, using)

@receiver(pre_save, sender=STRUCTURE, dispatch_uid="ticket_events.structure_before")
@receiver(pre_save, sender=OFFICE, dispatch_uid="ticket_events.office_before")
def related_before(sender, instance, using, raw=False, update_fields=None, **kwargs):
    if raw:
        return
    before = {}
    if instance.pk and (update_fields is None or "name" in update_fields):
        old = sender._default_manager.using(using).filter(pk=instance.pk).values("name").first()
        if old is not None and old["name"] != instance.name:
            before = related_snapshots(sender, instance, using)
    setattr(instance, STATE, before)

@receiver(post_save, sender=STRUCTURE, dispatch_uid="ticket_events.structure_saved")
@receiver(post_save, sender=OFFICE, dispatch_uid="ticket_events.office_saved")
def related_saved(sender, instance, using, raw=False, **kwargs):
    if raw:
        return
    before = getattr(instance, STATE, {})
    if hasattr(instance, STATE):
        delattr(instance, STATE)
    for category_id, old_content in before.items():
        report("post_save", sender, instance.pk, category_id,
               old_content, snapshot(category_id, using), using)

@receiver(pre_delete, sender=OFFICE, dispatch_uid="ticket_events.office_deleting")
def office_deleting(sender, instance, using, **kwargs):
    # SET_NULL does not call TicketCategory.save(): capture affected rows here.
    setattr(instance, STATE, related_snapshots(sender, instance, using))

@receiver(post_delete, sender=OFFICE, dispatch_uid="ticket_events.office_deleted")
def office_deleted(sender, instance, using, **kwargs):
    before = getattr(instance, STATE, {})
    if hasattr(instance, STATE):
        delattr(instance, STATE)
    for category_id, old_content in before.items():
        report("post_delete", sender, instance.pk, category_id,
               old_content, snapshot(category_id, using), using)
