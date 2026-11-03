"""PROTOTIPO UI/API LOCALE DI VERIFICA — NON UI ufficiale UniTicket.

Banco di prova per i receiver con i modelli originali. Non usare queste view
o URL in produzione: non replicano l'interfaccia o i permessi ufficiali.
"""
import json
from pathlib import Path
from uuid import uuid4
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from organizational_area.models import OrganizationalStructure, OrganizationalStructureOffice
from uni_ticket.models import TicketCategory
from .content import snapshot, embedding_text

if not getattr(settings, "RECEIVER_DEMO", False):
    raise ImproperlyConfigured("Only use the dedicated demo settings.")
SLUG = "receiver-demo-only"

def structure():
    return OrganizationalStructure.objects.get_or_create(
        slug=SLUG, defaults={"name": "Dipartimento di prova", "unique_code": "RECEIVER-DEMO"})[0]

def payload(request, allowed, required):
    if request.content_type != "application/json":
        raise ValueError("Usare application/json")
    try:
        data = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        raise ValueError("JSON non valido")
    if not isinstance(data, dict) or set(data) - set(allowed) or set(required) - set(data):
        raise ValueError("Campi non validi; richiesti: " + ", ".join(required))
    for key, value in data.items():
        if key == "office_id":
            if value is not None and (type(value) is not int or value < 1):
                raise ValueError("office_id deve essere un ID positivo oppure null")
        elif not isinstance(value, str):
            raise ValueError(key + " deve essere una stringa")
    if "name" in data and not data["name"].strip():
        raise ValueError("Nome obbligatorio")
    return data

def error(exc):
    return JsonResponse({"error": exc.message_dict if hasattr(exc, "message_dict") else str(exc)}, status=400)

def serialize(category):
    content = snapshot(category.pk, category._state.db)
    return {"id": category.pk, "name": category.name, "description": category.description,
            "office_id": category.organizational_office_id, "content": content,
            "embedding_text": embedding_text(content)}

def office_for(value, owner):
    return None if value is None else get_object_or_404(
        OrganizationalStructureOffice, pk=value, organizational_structure=owner)

@ensure_csrf_cookie
@require_http_methods(["GET"])
def home(request):
    return HttpResponse(Path(__file__).with_name("demo.html").read_text(encoding="utf-8-sig"))

@require_http_methods(["GET", "POST"])
def categories(request):
    if request.method == "GET":
        rows = TicketCategory.objects.filter(organizational_structure__slug=SLUG)
        return JsonResponse({"categories": [serialize(c) for c in rows]})
    try:
        data = payload(request, ("name", "description", "office_id"), ("name", "description"))
        with transaction.atomic():
            owner = structure()
            category = TicketCategory(name=data["name"], description=data["description"],
                slug="demo-" + uuid4().hex, organizational_structure=owner,
                organizational_office=office_for(data.get("office_id"), owner))
            category.full_clean()
            category.save()
            result = serialize(category)
        return JsonResponse(result, status=201)
    except (ValueError, ValidationError) as exc:
        return error(exc)

@require_http_methods(["GET", "PUT", "DELETE"])
def category_detail(request, pk):
    try:
        with transaction.atomic():
            category = get_object_or_404(TicketCategory, pk=pk, organizational_structure__slug=SLUG)
            if request.method == "GET":
                return JsonResponse(serialize(category))
            if request.method == "DELETE":
                if not category.can_be_deleted():
                    return JsonResponse({"error": "Richieste collegate"}, status=409)
                category.delete()
                result = {"deleted": pk}
            else:
                data = payload(request, ("name", "description", "office_id"), ("name", "description"))
                category.name, category.description = data["name"], data["description"]
                fields = ["name", "description", "modified"]
                if "office_id" in data:
                    category.organizational_office = office_for(data["office_id"], category.organizational_structure)
                    fields.append("organizational_office")
                category.full_clean()
                category.save(update_fields=fields)
                result = serialize(category)
        return JsonResponse(result)
    except (ValueError, ValidationError) as exc:
        return error(exc)

@require_http_methods(["GET", "PUT"])
def context(request):
    try:
        if request.method == "PUT":
            data = payload(request, ("name",), ("name",))
            with transaction.atomic():
                owner = structure()
                owner.name = data["name"]
                owner.full_clean()
                owner.save(update_fields=["name"])
        owner = OrganizationalStructure.objects.filter(slug=SLUG).first()
        offices = [] if owner is None else list(owner.get_offices().values("id", "name", "is_default"))
        return JsonResponse({"structure": None if owner is None else {"id": owner.pk, "name": owner.name}, "offices": offices})
    except (ValueError, ValidationError) as exc:
        return error(exc)

@require_http_methods(["POST"])
def offices(request):
    try:
        data = payload(request, ("name",), ("name",))
        with transaction.atomic():
            office = OrganizationalStructureOffice(name=data["name"], slug="demo-" + uuid4().hex,
                organizational_structure=structure())
            office.full_clean()
            office.save()
        return JsonResponse({"id": office.pk, "name": office.name}, status=201)
    except (ValueError, ValidationError) as exc:
        return error(exc)

@require_http_methods(["PUT", "DELETE"])
def office_detail(request, pk):
    try:
        with transaction.atomic():
            office = get_object_or_404(OrganizationalStructureOffice, pk=pk,
                                      organizational_structure__slug=SLUG)
            if office.is_default:
                return JsonResponse({"error": "Usare un ufficio creato per la prova, non quello predefinito"}, status=409)
            if request.method == "PUT":
                data = payload(request, ("name",), ("name",))
                office.name = data["name"]
                office.full_clean()
                office.save(update_fields=["name"])
                result = {"id": office.pk, "name": office.name}
            else:
                from uni_ticket.utils import office_can_be_deleted
                if not office_can_be_deleted(office):
                    return JsonResponse({"error": "Ufficio non eliminabile"}, status=409)
                office.delete()
                result = {"deleted": pk}
        return JsonResponse(result)
    except (ValueError, ValidationError) as exc:
        return error(exc)
