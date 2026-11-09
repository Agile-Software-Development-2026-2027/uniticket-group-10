"""Prototipo UI condiviso: sola lettura; tutte le scritture usano UniTicket."""
import json
from django.conf import settings
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_GET
from organizational_area.models import OrganizationalStructure
from uni_ticket.forms import CategoryForm
from uni_ticket.models import TicketCategory
from uni_ticket.utils import user_is_manager
from ticket_events.content import snapshot


@require_GET
def prototype(request):
    if not getattr(settings, "RECEIVER_DEMO", False):
        raise Http404("Prototipo disponibile soltanto nel laboratorio locale")
    context = {"cards": [], "visible_fields": (
        "name", "description", "allow_user", "allow_employee", "allow_anonymous", "allow_guest", "allow_spid_cie",
    )}
    if request.user.is_authenticated:
        structure = get_object_or_404(OrganizationalStructure, slug="receiver-demo-only")
        if not user_is_manager(request.user, structure):
            return HttpResponseForbidden("Accedere con il manager locale receiver-manager.")
        parameters = {"structure_slug": structure.slug}
        context["create_form"] = CategoryForm()
        context["create_url"] = reverse("uni_ticket:manager_category_add_new", kwargs=parameters)
        # La pagina legge solo la struttura del laboratorio e non esegue save/delete.
        for category in TicketCategory.objects.filter(organizational_structure=structure):
            category_parameters = {**parameters, "category_slug": category.slug}
            context["cards"].append({
                "category": category,
                "form": CategoryForm(instance=category),
                "edit_url": reverse("uni_ticket:manager_category_edit", kwargs=category_parameters),
                "delete_url": reverse("uni_ticket:manager_delete_category", kwargs=category_parameters),
                "state": json.dumps(snapshot(category.pk, "default"), ensure_ascii=False, indent=2),
            })
    return render(request, "receiver_lab/index.html", context)
