"""Catalogo delle richieste proponibili all'utente dell'assistente."""

import re
from collections import Counter
from typing import Dict, Iterable, List

from api_rest.authorizations import AuthorizationToken
from api_rest.serializers import OrganizationalStructureSerializer
from django.urls import reverse
from django.utils import timezone
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from uni_ticket.models import Ticket, TicketCategory, TicketCategoryInputList, TicketCategoryModule
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


def available_categories(user, *, category_id=None, excluded_category_ids=(), structure_ids=()) -> List[TicketCategory]:
    """Return accessible categories, optionally filtering IDs, exclusions and structures."""
    categories = category_queryset()
    # Permette allo schema di verificare un solo ID con gli stessi filtri della chat.
    if category_id is not None:
        categories = categories.filter(pk=category_id)
    if excluded_category_ids:
        categories = categories.exclude(pk__in=excluded_category_ids)
    if structure_ids:
        categories = categories.filter(organizational_structure_id__in=structure_ids)

    return [category for category in categories if category.allowed_to_user(user)[0]]

# Campi che uniTicket aggiunge a ogni modulo: non dicono nulla di un modulo in particolare.
SYSTEM_FIELD_LABELS = frozenset({
    "oggetto della richiesta", "descrizione",
    "dichiaro di aver letto e compreso quanto scritto sopra e di assumermi ogni responsabilità su quanto dichiarato",
})
# Un campo presente in più moduli di così ("Cognome", "Matricola") non distingue nessuno.
MAX_FORMS_PER_LABEL = 3
# Le etichette più corte o più lunghe di così sono sigle o frasi intere, non nomi di campi.
MIN_LABEL_CHARS = 4
MAX_LABEL_CHARS = 90
HIDDEN_FIELD = "CustomHiddenField"
_WHITESPACE = re.compile(r"\s+")


def field_labels(categories: Iterable[TicketCategory]) -> Dict[int, List[str]]:
    """Le etichette dei campi visibili del modulo attivo di ogni categoria, nell'ordine del form.

    Se una categoria ha più moduli attivi vale il più recente, come in uniTicket.
    """
    module_of = {}
    for module in TicketCategoryModule.objects.filter(
        ticket_category__in=list(categories), is_active=True,
    ).order_by("created"):
        module_of[module.ticket_category_id] = module.pk
    category_of = {module: category for category, module in module_of.items()}
    labels: Dict[int, List[str]] = {category: [] for category in module_of}
    for field in TicketCategoryInputList.objects.filter(
        category_module__in=list(category_of),
    ).exclude(field_type=HIDDEN_FIELD).order_by("category_module_id", "ordinamento", "pk"):
        label = _WHITESPACE.sub(" ", field.name.replace("\xa0", " ")).strip()
        labels[category_of[field.category_module_id]].append(label)
    return labels


def distinctive_field_labels(categories: Iterable[TicketCategory]) -> Dict[int, List[str]]:
    """Per ogni categoria, i campi che la distinguono dalle altre del catalogo.

    Restano fuori i campi di sistema e quelli presenti in più di MAX_FORMS_PER_LABEL moduli: "Altri
    componenti del nucleo familiare attualmente iscritti" distingue un esonero, "Matricola" no.
    """
    every = field_labels(category_queryset())
    forms_with = Counter(label.lower() for labels in every.values() for label in set(labels))
    wanted = {category.pk for category in categories}
    return {
        category: [
            label for label in labels
            if MIN_LABEL_CHARS <= len(label) <= MAX_LABEL_CHARS
            and label.lower() not in SYSTEM_FIELD_LABELS
            and forms_with[label.lower()] <= MAX_FORMS_PER_LABEL
        ]
        for category, labels in every.items() if category in wanted
    }


class AvailableCategorySerializer(serializers.ModelSerializer):
    """Una categoria per l'agente. `field_labels` arriva dal contesto (`distinctive_field_labels`),
    calcolato una volta per tutta la lista: senza, resta vuoto."""

    structure_id = serializers.IntegerField(source="organizational_structure_id", read_only=True)
    structure_name = serializers.CharField(source="organizational_structure.name", read_only=True)
    url = serializers.SerializerMethodField()
    audience = serializers.SerializerMethodField()
    field_labels = serializers.SerializerMethodField()

    class Meta:
        model = TicketCategory
        fields = ("id", "name", "description", "structure_id", "structure_name", "url", "audience", "field_labels")

    def get_audience(self, category):
        """A chi è aperta la categoria, come la configura la struttura."""
        return {
            "students": category.allow_user,
            "staff": category.allow_employee,
            "guests": category.allow_guest,
            "anonymous": category.allow_anonymous,
        }

    def get_field_labels(self, category):
        return self.context.get("field_labels", {}).get(category.pk, [])

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

    def list(self, request, *args, **kwargs):
        categories = self.get_queryset()
        context = {**self.get_serializer_context(), "field_labels": distinctive_field_labels(categories)}
        return Response(AvailableCategorySerializer(categories, many=True, context=context).data)

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
