"""Demo retrieval; replace with the real search service when ready."""

from .replies import TicketReply


demo_ticket_categories : list[TicketReply]=[
    {"type": "ticket", "label": "Certificato di iscrizione",
     "title": "Richiesta Certificato di Iscrizione", "ticket_id": 316, "structure_name": "DiBEST"},
    {"type": "ticket", "label": "Richiesta certificato di iscrizione/Laurea/Diploma Supplement",
     "title": "Richiesta certificato di iscrizione/Laurea/Diploma Supplement", "ticket_id": 317, "structure_name": "DIMES"},
    {"type": "ticket", "label": "Certificato di laurea",
     "title": "Richiesta certificato di laurea", "ticket_id": 318, "structure_name": "DiBEST"},
    {"type": "ticket", "label": "Richiesta Certificato Uso Estero/Questura - Certificate Foreign Use/Questura",
     "title": "Richiesta Certificato Uso Estero/Questura - Certificate Foreign Use/Questura", "ticket_id": 319, "structure_name": "Servizi Didattici"},
    {"type": "ticket", "label": "Chiusura Erasmus Studio",
     "title": "Richiesta Chiusura Erasmus Studio", "ticket_id": 321, "structure_name": "DIAm"},
]


def search(query: str) -> list[TicketReply]:
    if query.casefold() == "nessun risultato":
        return []
    return demo_ticket_categories
