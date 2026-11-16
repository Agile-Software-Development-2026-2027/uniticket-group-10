"""Lettura dei dati persistiti secondo il contratto di indicizzazione."""

from uni_ticket.models import TicketCategory

from .index_fields import INDEX_FIELDS


# Legge dal database i campi osservati di una categoria.
def snapshot(category_id, using):
    """Conserva i valori originali, inclusi None, booleani e chiavi esterne."""
    return (
        # Usa lo stesso database dell’operazione che ha emesso il signal.
        TicketCategory.objects.using(using)
        .filter(pk=category_id)  # Cerca la categoria tramite ID.
        .values(*INDEX_FIELDS)  # Restituisce solo i campi che confrontiamo.
        .first()  # Restituisce il dizionario, oppure None se la categoria manca.
    )


# Unisce nome e descrizione con una riga a capo, senza aggiungere metadata.
def embedding_text(content):
    """Costruisce il testo inviato al modello usando nome e descrizione."""
    # Usa testo vuoto quando il valore è None.
    name = content["name"] or ""
    description = content["description"] or ""
    return f"{name}\n{description}"


# Legge le categorie collegate a un ufficio prima della sua eliminazione.
def office_snapshots(office_id, using):
    """Conserva le categorie interessate prima del SET_NULL sull’ufficio."""
    rows = (
        # Usa lo stesso database dell’operazione che ha emesso il signal.
        TicketCategory.objects.using(using)
        .filter(organizational_office_id=office_id)
        .values("pk", *INDEX_FIELDS)
    )
    previous_categories = {}
    for row in rows:
        # Separa l’ID dai dati da confrontare.
        category_id = row.pop("pk")
        # Associa ogni ID ai vecchi dati della relativa categoria.
        previous_categories[category_id] = row
    return previous_categories
