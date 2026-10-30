from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseBase
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from uni_ticket.models import TicketCategory
from uni_ticket.utils import base_context
from uni_ticket.views.user import TicketAddNew

def _get_selected_category(request):
    ticket_id = request.GET.get("ticket_id")
    if not ticket_id:
        return None
    try:
        category_id = int(ticket_id)
    except ValueError:
        raise Http404("Tipologia di richiesta non valida")
    return get_object_or_404(TicketCategory, pk=category_id)


def _reset_conversation(request):
    request.session.pop("assistant_messages", None)
    return redirect("assistant_workspace")


def _send_message(request, selected_category):
    text = request.POST.get("message", "").strip()
    if text:
        history = request.session.get("assistant_messages", [])
        history.append(text[:500])
        request.session["assistant_messages"] = history
    url = reverse("assistant_workspace")
    if selected_category:
        url += f"?ticket_id={selected_category.pk}"
    return redirect(url + "#chatbot-query")


def _get_ticket_form(request, selected_category):
    """Restituisce il contesto del form o la risposta della view originale."""
    if not selected_category:
        if request.method == "POST":
            raise Http404("Seleziona una tipologia di richiesta")
        return {}

    ticket_view = TicketAddNew()
    ticket_view.setup(request)
    handler = ticket_view.post if request.method == "POST" else ticket_view.get
    return handler(
        request,
        structure_slug=str(selected_category.organizational_structure_id),
        category_slug=str(selected_category.pk),
        api=True,
    )


@login_required
@require_http_methods(["GET", "POST"])
def workspace(request):
    action = request.POST.get("_assistant_action")
    if request.method == "POST" and action == "reset":
        return _reset_conversation(request)

    selected_category = _get_selected_category(request)
    if request.method == "POST" and action == "message":
        return _send_message(request, selected_category)

    ticket_form = _get_ticket_form(request, selected_category)
    if isinstance(ticket_form, HttpResponseBase):
        return ticket_form

    context = base_context({
        "chat_messages": request.session.get("assistant_messages", []),
        "selected_ticket_id": selected_category.pk if selected_category else None,
    })
    context.update(ticket_form)
    return render(request, "workspace.html", context)
