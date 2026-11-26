"""Validazione dei dati compilati dall'agente per le categorie accessibili nella chat."""

from api_rest.authorizations import AuthorizationToken
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import NotFound
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from uni_ticket.models import TicketCategoryModule

from .catalog import available_categories
from .form_validation import validate_form



class AgentSessionAuthentication(SessionAuthentication):
    def enforce_csrf(self, request):
        return


class FormValidationRequestSerializer(serializers.Serializer):
    data = serializers.DictField()


class CategoryFormValidationView(APIView):
    authentication_classes = [AuthorizationToken, AgentSessionAuthentication]
    permission_classes = [IsAuthenticated]

    parser_classes = [JSONParser]

    def post(self, request, category_id: int):
        body = FormValidationRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)

        categories = available_categories(request.user, category_id=category_id)
        if not categories:
            raise NotFound("Categoria non disponibile.")
        category = categories[0]

        try:
            module = get_object_or_404(TicketCategoryModule, ticket_category=category, is_active=True)
        except TicketCategoryModule.MultipleObjectsReturned:
            return Response({"detail": "La categoria ha più moduli attivi."}, status=409)

        form = module.get_form(
            data=body.validated_data["data"],
            remove_filefields=True,
            show_conditions=True,
            current_user=request.user,
        )
        return Response(validate_form(form))