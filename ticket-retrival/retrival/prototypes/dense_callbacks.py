"""Callback che compongono il testo dei ticket da indicizzare con Dense."""

from ..base import Ticket


"""Genera embeddings per title, descrizione e struttura"""
def title_description_structure(ticket: Ticket) -> str:
    title = ticket.title.strip()
    description = (ticket.description or "").strip()
    structure = (ticket.structure.get("name") or "").strip()
    return f"Titolo: {title}\nDescrizione: {description}\nStruttura: {structure}"

def title_description_structure_fields(ticket: Ticket) -> str:
    text = title_description_structure(ticket)
    if not ticket.fields:
        raise ValueError(
            f"Il ticket {ticket.ticket_category_id} non contiene campi del form"
        )
    fields = ", ".join(form_field.name.strip() for form_field in ticket.fields)
    return f"{text}\nCampi del modulo: {fields}"

def title_description_queries(ticket: Ticket) -> str:
    pass
