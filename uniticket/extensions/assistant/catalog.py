"""Catalogo delle richieste proponibili all'utente dell'assistente."""

from api_rest.authorizations import AuthorizationToken
from api_rest.serializers import (
    TicketCategorySerializer,
)
from django.urls import reverse
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from uni_ticket.models import Ticket, TicketCategory


def available_categories(user):
    if Ticket.number_limit_reached_by_user(user):
        return []

    categories = TicketCategory.objects.filter(
        is_active=True,
        is_hidden=False,
        organizational_structure__is_active=True,
        organizational_office__is_active=True,
        ticketcategorymodule__is_active=True,
    ).select_related("organizational_structure", "organizational_office").distinct()

    available = []
    for category in categories:
        if not category.is_published() or not category.allowed_to_user(user)[0]:
            continue
        if not category.user_can_open_tickets(user):
            continue
        if not category.user_multiple_open_tickets and Ticket.existent_open_ticket(user, category):
            continue
        if category.max_requests_per_user and Ticket.objects.filter(
            created_by=user, input_module__ticket_category=category,
        ).count() >= category.max_requests_per_user:
            continue
        available.append(category)
    return available


class AvailableCategorySerializer(TicketCategorySerializer):
    structure_name = serializers.CharField(source="organizational_structure.name", read_only=True)
    url = serializers.SerializerMethodField()

    def get_url(self, category):
        return reverse("uni_ticket:add_new_ticket", kwargs={
            "structure_slug": category.organizational_structure.slug,
            "category_slug": category.slug,
        })


class AvailableCategoriesView(ListAPIView):
    authentication_classes = [AuthorizationToken, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = AvailableCategorySerializer

    def get_queryset(self):
        return available_categories(self.request.user)
