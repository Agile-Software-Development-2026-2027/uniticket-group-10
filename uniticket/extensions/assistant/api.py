"""Static search demo. Replace the mock responses when the classifier is ready."""
import json

from django.http import JsonResponse
from django.views.decorators.http import require_POST


@require_POST
# Endpoint JSON della demo: riceve una query e restituisce tipologie o un chiarimento.
def search(request):
    # Gli errori restano JSON, così il client della chat può gestirli senza ricevere una pagina HTML.
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Accedi nuovamente."}, status=401)
    if request.content_type != "application/json":
        return JsonResponse({"error": "Invia un payload JSON."}, status=415)
    try:
        payload = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "JSON non valido."}, status=400)
    # Il contratto accetta un oggetto con query testuale non vuota, fino a 500 caratteri.
    query = payload.get("query") if isinstance(payload, dict) else None
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 500:
        return JsonResponse({"error": "Inserisci una query tra 1 e 500 caratteri."}, status=400)

    # Le parole chiave selezionano soltanto scenari dimostrativi.
    # La ricerca non consulta database o classificatore e non mantiene contesto tra le query.
    query = query.strip().casefold()
    # Il client visualizza clarify come messaggio e quick_replies come pulsanti di ricerca.
    if query in {"clarify", "dipartimento"}:
        return JsonResponse({
            "clarify": "Quale dipartimento ti interessa?",
            "quick_replies": ["DeMaCS", "DiMeS"],
        })
    # Una lista vuota è una risposta valida: indica assenza di corrispondenze.
    if query in {"nessun risultato", "no match"}:
        return JsonResponse({"tickets": []})
    # Gli ID statici indicano tipologie della fixture locale; selezionarli non crea ticket.
    return JsonResponse({"tickets": [
        {"id": 316, "title": "Richiesta Certificato di Iscrizione"},
        {"id": 317, "title": "Richiesta certificato di iscrizione/Laurea/Diploma Supplement"},
        {"id": 318, "title": "Richiesta certificato di laurea"},
        {"id": 319, "title": "Richiesta Certificato Uso Estero/Questura - Certificate Foreign Use/Questura"},
        {"id": 321, "title": "Richiesta Chiusura Erasmus Studio"},
    ]})
