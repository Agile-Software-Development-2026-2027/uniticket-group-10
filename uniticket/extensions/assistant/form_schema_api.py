"""Lettura dello schema per le categorie accessibili nella chat."""

from api_rest.authorizations import AuthorizationToken
from django.shortcuts import get_object_or_404
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from uni_ticket.models import TicketCategoryModule

from .catalog import available_categories
from .form_schema import build_form_schema


class CategoryFormSchemaView(APIView):
    # Usa gli stessi metodi di autenticazione del catalogo e della ricerca.
    authentication_classes = [AuthorizationToken, SessionAuthentication]
    permission_classes = [IsAuthenticated]

    # Verifica l'accesso, costruisce il form originale e restituisce il suo schema.
    def get(self, request, category_id: int):
        categories = available_categories(request.user, category_id=category_id)
        if not categories:
            raise NotFound("Categoria non disponibile.")
        category = categories[0]
        try:
            module = get_object_or_404(TicketCategoryModule, ticket_category=category, is_active=True)
        except TicketCategoryModule.MultipleObjectsReturned:
            # La vista originale richiede un solo modulo attivo: non ne scegliamo uno arbitrariamente.
            return Response({"detail": "La categoria ha più moduli attivi."}, status=409)
        form = module.get_form(show_conditions=True, current_user=request.user)
        schema = build_form_schema(form, category_id=category.pk, module_id=module.pk)
        return Response(schema)
