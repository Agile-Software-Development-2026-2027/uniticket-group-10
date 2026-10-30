

# versione in cui il post invia le 5 categorie più pertinenti
import json


from django.http import JsonResponse
from django.views.decorators.http import require_POST
#importo il tipo (formato) che ha definito angelo
from .replies import TicketReply


# categorie attive presenti nei dati di prova in dumps/local_conf.json
demo_ticket_categories : list[TicketReply]=[
    {"type": "ticket", "label": "Certificato di iscrizione",
     "title": "Richiesta Certificato di Iscrizione", "ticket_id": 316},
    {"type": "ticket", "label": "Iscrizione / Laurea / Diploma Supplement",
     "title": "Richiesta certificato di iscrizione/Laurea/Diploma Supplement", "ticket_id": 317},
    {"type": "ticket", "label": "Certificato di laurea",
     "title": "Richiesta certificato di laurea", "ticket_id": 318},
    {"type": "ticket", "label": "Certificato uso estero / Questura",
     "title": "Richiesta Certificato Uso Estero/Questura - Certificate Foreign Use/Questura", "ticket_id": 319},
    {"type": "ticket", "label": "Chiusura Erasmus Studio",
     "title": "Richiesta Chiusura Erasmus Studio", "ticket_id": 321},
]



@require_POST
def search(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Accedi per utilizzare l'assistente"}, status=401)

    #controllo riceva un JSON valido
    try:
        payload = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "JSON non valido."}, status=400)


    if isinstance(payload,dict):
        #mi prendo il valore associato alla chiave query (sempre se esiste)
        query=payload.get("query")
    else:
        query=None

    # se la richiesta è una stringa vuota
    if not isinstance(query,str) or not query.strip():
        return JsonResponse({"error": "Scrivi una richiesta"}, status=400)

    #non ho ancora implementato la ricerca, quindi per ora restituisco sempre le stesse 5 categorie di ticket
    if query.strip().casefold()=="nessun risultato":
        return JsonResponse({"replies": []})
    
    return JsonResponse({"replies": demo_ticket_categories})

