"""Receiver CRUD delle definizioni, con notifiche eseguite dopo commit."""
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

@receiver(post_delete, sender=CATEGORY, dispatch_uid="ticket_events.category_deleted")
def category_deleted(sender, instance, using, **kwargs):
    """Notifica l’ID eliminato senza rileggere una riga già cancellata."""
    # Django può azzerare instance.pk prima del commit: partial conserva il valore.
    callback = partial(safe_notify, "DELETE", instance.pk)
    transaction.on_commit(callback, using=using)

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
