import json
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.urls import reverse
from django.utils.translation import get_language
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from uni_ticket.models import TicketCategory


def get_catalog(user) -> list[dict]:
    if not user.is_authenticated:
        return []
    categories = (
        TicketCategory.objects.filter(
            is_active=True,
            organizational_structure__is_active=True,
            organizational_office__is_active=True,
            ticketcategorymodule__is_active=True,
        )
        .select_related("organizational_structure")
        .prefetch_related("allowed_users", "allowed_users_lists__allowed_users")
        .distinct()
    )
    return [
        {
            "id": category.pk, "name": category.name, "description": category.description or "",
            "structure_name": category.organizational_structure.name, "hidden": category.is_hidden,
            "url": reverse("uni_ticket:add_new_ticket", kwargs={
                "structure_slug": category.organizational_structure.slug, "category_slug": category.slug,
            }),
        }
        for category in categories
        if category.is_published() and category.allowed_to_user(user)[0] and category.user_can_open_tickets(user)
    ]


class AgentUnavailable(RuntimeError):
    pass


def call_agent(data, *, user):
    catalog = get_catalog(user)
    payload = {"input": data, "catalog": catalog, "language": get_language() or "it"}
    request = Request(settings.ASSISTANT_AGENT_URL, data=json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json", "Accept": "application/json"}, method="POST")
    try:
        try:
            response = urlopen(request, timeout=30)
        except HTTPError as error:
            if error.code not in (400, 404, 422):
                error.close()
                raise
            response = error
        with response:
            if response.headers.get_content_type() != "application/json":
                raise ValueError("Expected a JSON response")
            return json.load(response), response.status
    except (URLError, OSError, HTTPException, ValueError) as error:
        raise AgentUnavailable("Agent service unavailable or invalid response") from error


class ConversationView(APIView):
    """
    Endpoint Django che funge da intermediario tra il frontend e il microservizio agentico.

    Frontend (Django) -> API Django -> Agent Microservice (LangGraph)

    Responsabilità:
    - Verificare che l'utente sia autenticato.
    - Inoltrare all'agente i dati ricevuti dal frontend.
    - Fornire la lingua dell'utente, utile per generare risposte LLM localizzate.
    - Recuperare e trasmettere le categorie di ticket accessibili all'utente (si potrebbe fare in un altro modo ma questo è il più semplice)
    - Restituire al frontend le risposte prodotte dall'agente.

    La comunicazione avviene tramite HTTP POST con richiesta e risposta JSON.
    La validazione del contenuto della richiesta appartiene all’agente.

    Django gestisce autenticazione e autorizzazione, mentre il microservizio LangGraph è responsabile della logica conversazionale.
    """

    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]
    renderer_classes = [JSONRenderer]

    def post(self, request):
        if not isinstance(request.data, dict):
            raise ValidationError({"detail": "Expected a JSON object"})

        try:
            data, status = call_agent(request.data, user=request.user)
        except AgentUnavailable:
            return Response({"detail": "Agent service unavailable"}, status=503)
        return Response(data, status=status)
