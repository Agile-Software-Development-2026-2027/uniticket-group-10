"""Catalogo delle richieste proponibili all'utente dell'assistente."""

from typing import List

from api_rest.authorizations import AuthorizationToken
from api_rest.serializers import OrganizationalStructureSerializer
from django.urls import reverse
from django.utils import timezone
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from uni_ticket.models import Ticket, TicketCategory
from django.db.models import Q, QuerySet


def category_queryset() -> QuerySet[TicketCategory]:
    """Return a lazily evaluated QuerySet of active, visible ticket categories."""
    # https://docs.djangoproject.com/en/6.0/ref/models/querysets/#when-querysets-are-evaluated
    now = timezone.now()
    return TicketCategory.objects.filter(
        Q(date_start__isnull=True) | Q(date_start__lte=now),
        Q(date_end__isnull=True) | Q(date_end__gt=now),
        is_active=True,
        is_hidden=False,
        organizational_structure__is_active=True,
        organizational_office__is_active=True,
        ticketcategorymodule__is_active=True,
    ).select_related("organizational_structure", "organizational_office").distinct()


def available_categories(user, *, excluded_category_ids=(), structure_ids=()) -> List[TicketCategory]:
    """Return categories accessible to the user, applying optional exclusions and structure filters."""
    categories = category_queryset()
    if excluded_category_ids:
        categories = categories.exclude(pk__in=excluded_category_ids)
    if structure_ids:
        categories = categories.filter(organizational_structure_id__in=structure_ids)

    return [category for category in categories if category.allowed_to_user(user)[0]]

class AvailableCategorySerializer(serializers.ModelSerializer):
    structure_id = serializers.IntegerField(source="organizational_structure_id", read_only=True)
    structure_name = serializers.CharField(source="organizational_structure.name", read_only=True)
    url = serializers.SerializerMethodField()

    class Meta:
        model = TicketCategory
        fields = ("id", "name", "description", "structure_id", "structure_name", "url")

    def get_url(self, category):
        return reverse("uni_ticket:add_new_ticket", kwargs={
            "structure_slug": category.organizational_structure.slug,
            "category_slug": category.slug,
        })


class AvailableCategoriesView(ListAPIView):
    authentication_classes = [AuthorizationToken, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = AvailableCategorySerializer
    pagination_class = None

    def get_queryset(self):
        return available_categories(self.request.user)

class AvailableStructuresView(ListAPIView):
    authentication_classes = [AuthorizationToken, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = OrganizationalStructureSerializer
    pagination_class = None
        
    def get_queryset(self):
        return list({
            category.organizational_structure_id: category.organizational_structure
            for category in available_categories(self.request.user)
        }.values())
