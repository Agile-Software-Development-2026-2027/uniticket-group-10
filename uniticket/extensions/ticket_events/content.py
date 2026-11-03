"""The agreed embedding input, independent of demo views and settings."""
from uni_ticket.models import TicketCategory

FIELDS = ("name", "description", "organizational_structure.name", "organizational_office.name")
DB_FIELDS = tuple(field.replace(".", "__") for field in FIELDS)

def snapshot(category_id, using):
    row = (TicketCategory.objects.using(using).filter(pk=category_id)
           .values(*DB_FIELDS).first())
    if row is None:
        return None
    return {field: row[db_field] or "" for field, db_field in zip(FIELDS, DB_FIELDS)}

def embedding_text(content):
    return "\n".join(f"{label}: {content[field]}" for label, field in zip(
        ("Servizio", "Descrizione", "Struttura", "Ufficio"), FIELDS
    ))

def related_snapshots(sender, instance, using):
    relation = "organizational_structure_id" if sender._meta.model_name == "organizationalstructure" else "organizational_office_id"
    ids = TicketCategory.objects.using(using).filter(**{relation: instance.pk}).values_list("pk", flat=True)
    return {pk: snapshot(pk, using) for pk in ids}
