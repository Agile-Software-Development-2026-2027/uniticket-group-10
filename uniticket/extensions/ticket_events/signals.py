"""Receiver permanenti per le modifiche delle categorie UniTicket."""
import logging
from functools import partial

from django.db import transaction
from django.db.models.signals import pre_save, post_save, pre_delete, post_delete
from django.dispatch import receiver
from uni_ticket.models import TicketCategory
from organizational_area.models import OrganizationalStructureOffice

from .content import snapshot, office_snapshots
from .notifications import safe_notify

logger = logging.getLogger("ticket_events")
# Nome dell’attributo che conserva i vecchi dati solo in memoria.
STATE = "_ticket_events_before"


# Legge i vecchi dati della categoria prima che Django salvi quelli nuovi.
@receiver(pre_save, sender=TicketCategory, dispatch_uid="ticket_events.category_before")
def category_before(sender, instance, using, raw=False, **kwargs):
    if not raw:  # Ignora i caricamenti di fixture.
        # Salva il prima sull’oggetto; senza ID usa None.
        setattr(instance, STATE, snapshot(instance.pk, using) if instance.pk else None)


# Dopo il salvataggio invia CREATE o UPDATE solo quando serve.
@receiver(post_save, sender=TicketCategory, dispatch_uid="ticket_events.category_saved")
def category_saved(sender, instance, created, using, raw=False, **kwargs):
    # Non elabora i dati caricati da fixture.
    if raw:
        return
    # Recupera i vecchi dati conservati prima del salvataggio.
    before = getattr(instance, STATE, None)
    if hasattr(instance, STATE):
        # Rimuove l’attributo temporaneo dopo averlo letto.
        delattr(instance, STATE)

    # Django indica se è stata inserita una nuova riga.
    if created:
        operation = "CREATE"
    else:
        # Senza il prima non può confrontare una modifica.
        if before is None:
            logger.warning("Stato precedente assente: category_id=%s", instance.pk)
            return
        # Legge dal DB i valori davvero salvati, anche se save() aggiorna pochi campi.
        after = snapshot(instance.pk, using)
        # Nessuna notifica se la categoria è assente o i dati osservati sono uguali.
        if after is None or before == after:
            return
        operation = "UPDATE"

    # Prepara operazione e ID; Django chiama safe_notify solo dopo il commit.
    transaction.on_commit(partial(safe_notify, operation, instance.pk), using=using)


# Dopo la cancellazione invia DELETE con l’ID della categoria eliminata.
@receiver(post_delete, sender=TicketCategory, dispatch_uid="ticket_events.category_deleted")
def category_deleted(sender, instance, using, **kwargs):
    # Conserva l’ID nella chiamata prima che Django lo tolga dall’oggetto.
    transaction.on_commit(partial(safe_notify, "DELETE", instance.pk), using=using)


# Prima di eliminare un ufficio legge le categorie che lo usano.
@receiver(pre_delete, sender=OrganizationalStructureOffice, dispatch_uid="ticket_events.office_deleting")
def office_deleting(sender, instance, using, **kwargs):
    # Conserva una mappa con ID categoria e vecchi dati.
    setattr(instance, STATE, office_snapshots(instance.pk, using))


# Dopo l’eliminazione dell’ufficio notifica le categorie rimaste senza ufficio.
@receiver(post_delete, sender=OrganizationalStructureOffice, dispatch_uid="ticket_events.office_deleted")
def office_deleted(sender, instance, using, **kwargs):
    # Recupera le categorie collegate prima della cancellazione dell’ufficio.
    before = getattr(instance, STATE, {})
    if hasattr(instance, STATE):
        # Rimuove l’attributo temporaneo dopo averlo letto.
        delattr(instance, STATE)
    for category_id, previous_state in before.items():
        # Rilegge la categoria dopo la rimozione del collegamento all’ufficio.
        current_state = snapshot(category_id, using)
        # Notifica solo le categorie ancora presenti e con dati cambiati.
        if current_state is not None and previous_state != current_state:
            # Conserva questo ID per la chiamata che avverrà al commit.
            transaction.on_commit(partial(safe_notify, "UPDATE", category_id), using=using)
