"""Lettura dei dati persistiti secondo il contratto di indicizzazione."""

from uni_ticket.models import TicketCategory

from .index_fields import INDEX_FIELDS


def snapshot(category_id, using):
    """Conserva i valori originali, inclusi None, booleani e chiavi esterne."""
    return (
        TicketCategory.objects.using(using)
        .filter(pk=category_id)
        .values(*INDEX_FIELDS)
        .first()
    )


def embedding_text(content):
    """Prepara l’anteprima testuale usando esclusivamente nome e descrizione."""
    name = content["name"] or ""
    description = content["description"] or ""
    return f"{name}\n{description}"


def office_snapshots(office_id, using):
    """Conserva le categorie interessate prima del SET_NULL sull’ufficio."""
    rows = (
        TicketCategory.objects.using(using)
        .filter(organizational_office_id=office_id)
        .values("pk", *INDEX_FIELDS)
    )
    previous_categories = {}
    for row in rows:
        category_id = row.pop("pk")
        previous_categories[category_id] = row
    return previous_categories
