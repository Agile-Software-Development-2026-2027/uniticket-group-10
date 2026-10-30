"""Static search demo. Replace the mock responses when the classifier is ready."""
import json

from django.http import JsonResponse
from django.views.decorators.http import require_POST


@require_POST
def search(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Accedi nuovamente."}, status=401)
    if request.content_type != "application/json":
        return JsonResponse({"error": "Invia un payload JSON."}, status=415)
    try:
        payload = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "JSON non valido."}, status=400)
    query = payload.get("query") if isinstance(payload, dict) else None
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 500:
        return JsonResponse({"error": "Inserisci una query tra 1 e 500 caratteri."}, status=400)

    # Demo switches only: no database, classifier or conversation state.
    query = query.strip().casefold()
    if query in {"clarify", "dipartimento"}:
        return JsonResponse({
            "clarify": "Quale dipartimento ti interessa?",
            "quick_replies": ["DeMaCS", "DiMeS"],
        })
    if query in {"nessun risultato", "no match"}:
        return JsonResponse({"tickets": []})
    return JsonResponse({"tickets": [
        {"id": 316, "title": "Richiesta Certificato di Iscrizione"},
        {"id": 317, "title": "Richiesta certificato di iscrizione/Laurea/Diploma Supplement"},
        {"id": 318, "title": "Richiesta certificato di laurea"},
        {"id": 319, "title": "Richiesta Certificato Uso Estero/Questura - Certificate Foreign Use/Questura"},
        {"id": 321, "title": "Richiesta Chiusura Erasmus Studio"},
    ]})
