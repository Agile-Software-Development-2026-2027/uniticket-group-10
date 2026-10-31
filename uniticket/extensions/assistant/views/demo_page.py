"""Layout della demo a pagina intera; i form sono caricati dalle viste originali UniTicket."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_GET

from uni_ticket.models import TicketCategory
from uni_ticket.utils import base_context


@login_required
@require_GET
def workspace(request, ticket_id=None):
    """Rende la chat e, per i segnalibri con categoria, indica il form da caricare via HTMX."""
    initial_module_url = ""
    if ticket_id is not None:
        category = get_object_or_404(TicketCategory.objects.select_related("organizational_structure"), pk=ticket_id)
        initial_module_url = reverse("uni_ticket:add_new_ticket", kwargs={
            "structure_slug": category.organizational_structure.slug,
            "category_slug": category.slug,
        })
    return render(request, "demo_page/workspace.html", base_context({"initial_module_url": initial_module_url}))
