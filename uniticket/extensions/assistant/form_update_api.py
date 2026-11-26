"""API per l'aggiornamento e la validazione di un singolo campo del form aperto."""

from api_rest.authorizations import AuthorizationToken
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from uni_ticket.models import TicketCategoryModule

from .catalog import available_categories
from .form_update import (
    DisabledFormFieldError,
    UnknownFormFieldError,
    check_updatable_field,
    validate_field_update,
)
from .form_validation_api import AgentSessionAuthentication


class FormFieldUpdateRequestSerializer(serializers.Serializer):
    field_id = serializers.CharField()
    value = serializers.JSONField(allow_null=True)
    data = serializers.DictField(required=False, default=dict)


class CategoryFormFieldUpdateView(APIView):
    authentication_classes = [AuthorizationToken, AgentSessionAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    def post(self, request, category_id: int):
        body = FormFieldUpdateRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)

        categories = available_categories(request.user, category_id=category_id)
        if not categories:
            raise NotFound("Categoria non disponibile.")
        category = categories[0]

        try:
            module = get_object_or_404(TicketCategoryModule, ticket_category=category, is_active=True)
        except TicketCategoryModule.MultipleObjectsReturned:
            return Response({"detail": "La categoria ha più moduli attivi."}, status=409)

        field_id = body.validated_data["field_id"]
        value = body.validated_data["value"]
        current_data = dict(body.validated_data["data"])

        unbound_form = module.get_form(
            remove_filefields=True,
            show_conditions=True,
            current_user=request.user,
        )
        try:
            check_updatable_field(unbound_form, field_id)
        except UnknownFormFieldError as exc:
            return Response(
                {
                    "valid": False,
                    "field_id": field_id,
                    "value": value,
                    "errors": [{"field": field_id, "code": "unknown_field", "message": str(exc)}],
                },
                status=400,
            )
        except DisabledFormFieldError as exc:
            return Response(
                {
                    "valid": False,
                    "field_id": field_id,
                    "value": value,
                    "errors": [{"field": field_id, "code": "disabled_field", "message": str(exc)}],
                },
                status=400,
            )

        bound_form = module.get_form(
            data={**current_data, field_id: value},
            remove_filefields=True,
            show_conditions=True,
            current_user=request.user,
        )
        return Response(validate_field_update(bound_form, field_id, value), status=200)