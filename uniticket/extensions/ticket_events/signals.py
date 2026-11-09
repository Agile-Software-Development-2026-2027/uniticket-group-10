"""Unico punto dei nostri receiver: CRUD originale e diagnostica di prova."""
import logging
from functools import partial

from django.conf import settings
from django.db import transaction
from django.db.models.signals import pre_save, post_save, pre_delete, post_delete
from django.dispatch import receiver

from .content import snapshot, office_snapshots
from .notifications import safe_notify, log_notification

logger = logging.getLogger("ticket_events")
CATEGORY = "uni_ticket.TicketCategory"
OFFICE = "organizational_area.OrganizationalStructureOffice"
STATE = "_ticket_events_before"


def received_event(signal_name, sender, category_id, operation, before, after, possible_action):
    """Conserva testo e metadata completi, anche quando cambia un solo campo."""
    # Il confronto decide se c’è un cambiamento; il report conserva tutti i dati concordati.
    return {
        "signal": signal_name,
        "source_model": sender.__name__,
        "category_id": category_id,
        "operation": operation,
        "possible_action": possible_action,
        "before": before,
        "after": after,
    }


@receiver(pre_save, sender=CATEGORY, dispatch_uid="ticket_events.category_before")
def category_before(sender, instance, using, raw=False, **kwargs):
    if not raw:
        setattr(instance, STATE, snapshot(instance.pk, using) if instance.pk else None)


@receiver(post_save, sender=CATEGORY, dispatch_uid="ticket_events.category_saved")
def category_saved(sender, instance, created, using, raw=False, **kwargs):
    if raw:  # Durante loaddata i dati correlati possono essere ancora incompleti.
        return
    before = getattr(instance, STATE, None)
    if hasattr(instance, STATE):
        delattr(instance, STATE)
    if not created and before is None:
        logger.warning("Stato precedente assente: category_id=%s", instance.pk)
        return
    # La rilettura considera soltanto ciò che save(update_fields=...) ha persistito.
    after = snapshot(instance.pk, using)
    if created:
        event = received_event("post_save", sender, instance.pk, "CREATE", None, after, "INDEX")
        transaction.on_commit(partial(safe_notify, "CREATE", instance.pk, event=event), using=using)
    elif after is not None and before != after:
        event = received_event("post_save", sender, instance.pk, "UPDATE", before, after, "REINDEX")
        transaction.on_commit(partial(safe_notify, "UPDATE", instance.pk, event=event), using=using)
    elif after is not None and getattr(settings, "RECEIVER_DEMO", False):
        # Nel laboratorio NONE rende visibile il salvataggio senza notificare l’indicizzatore.
        event = received_event("post_save", sender, instance.pk, "UPDATE", before, after, "NONE")
        transaction.on_commit(partial(log_notification, "UPDATE", instance.pk, event=event), using=using)


@receiver(pre_delete, sender=CATEGORY, dispatch_uid="ticket_events.category_deleting")
def category_deleting(sender, instance, using, **kwargs):
    # I valori vanno letti prima della cancellazione, anche per istanze con campi differiti.
    setattr(instance, STATE, snapshot(instance.pk, using))


@receiver(post_delete, sender=CATEGORY, dispatch_uid="ticket_events.category_deleted")
def category_deleted(sender, instance, using, **kwargs):
    before = getattr(instance, STATE, None)
    if hasattr(instance, STATE):
        delattr(instance, STATE)
    event = received_event("post_delete", sender, instance.pk, "DELETE", before, None, "REMOVE")
    # partial conserva l’ID anche quando Django azzera instance.pk prima del commit.
    transaction.on_commit(partial(safe_notify, "DELETE", instance.pk, event=event), using=using)


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
        if current_state is not None and previous_state != current_state:
            # L’origine reale è la cancellazione dell’ufficio, l’effetto sulla categoria è UPDATE.
            event = received_event(
                "post_delete", sender, category_id, "UPDATE", previous_state, current_state, "REINDEX",
            )
            transaction.on_commit(partial(safe_notify, "UPDATE", category_id, event=event), using=using)
