from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseBase
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from uni_ticket.models import TicketCategory
from uni_ticket.utils import base_context
from uni_ticket.views.user import TicketAddNew

# ticket_id identifica una tipologia TicketCategory, non una richiesta già creata.
def _get_selected_category(request):
    ticket_id = request.GET.get("ticket_id")
    if not ticket_id:
        return None
    try:
        category_id = int(ticket_id)
    except ValueError:
        raise Http404("Tipologia di richiesta non valida")
    # La tipologia deve esistere; disponibilità e permessi vengono poi verificati da TicketAddNew.
    return get_object_or_404(TicketCategory, pk=category_id)


# Elimina la cronologia di compatibilità lato server; search.js cancella quella della scheda.
def _reset_conversation(request):
    request.session.pop("assistant_messages", None)
    return redirect("assistant_workspace")


# Percorso POST tradizionale: registra il testo e conserva la tipologia selezionata nel redirect.
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


def _get_ticket_form(request, selected_category, *, fragment=False):
    """Restituisce il contesto del form o la risposta della view originale."""
    if not selected_category:
        if request.method == "POST":
            raise Http404("Seleziona una tipologia di richiesta")
        return {}

    # La classe originale mantiene controlli di accesso, validazione, salvataggio e notifiche.
    ticket_view = TicketAddNew()
    ticket_view.setup(request)
    handler = ticket_view.post if request.method == "POST" else ticket_view.get
    # api=True restituisce il contesto del form, oppure la risposta originale in caso di diniego/redirect.
    result = handler(
        request,
        structure_slug=str(selected_category.organizational_structure_id),
        category_slug=str(selected_category.pk),
        api=True,
    )
    # Solo per i frammenti HTMX, il redirect di creazione diventa un pannello di conferma.
    # Il normale POST della pagina completa conserva invece la risposta originale.
    created = getattr(ticket_view, "ticket", None)
    if fragment and created is not None and isinstance(result, HttpResponseBase) and result.status_code in (302, 303):
        return {"created_ticket": created, "ticket_detail_url": result.url}
    return result


@login_required
@require_http_methods(["GET", "POST"])
# Serve la pagina completa e mantiene disponibili reset, messaggi e invio senza HTMX.
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

    # Integra i dati della chat con il contesto del modulo eventualmente selezionato.
    context = base_context({
        "chat_messages": request.session.get("assistant_messages", []),
        "selected_ticket_id": selected_category.pk if selected_category else None,
    })
    context.update(ticket_form)
    return render(request, "workspace.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def ticket_form(request):
    """Load or submit the selected form; return HTML for the HTMX panel."""
    selected_category = _get_selected_category(request)
    if selected_category is None:
        raise Http404("Seleziona una tipologia di richiesta")
    # GET prepara il modulo; POST usa lo stesso percorso originale per validarlo e inviarlo.
    ticket_form = _get_ticket_form(request, selected_category, fragment=True)
    if isinstance(ticket_form, HttpResponseBase):
        return ticket_form
    if not ticket_form.get("form") and not ticket_form.get("created_ticket"):
        raise Http404("Modulo non disponibile")
    context = base_context(ticket_form)
    # La radice minimale esclude il layout completo dalla risposta destinata al pannello.
    context["base_template"] = "ticket_fragment_base.html"
    context["fragment_response"] = True
    # Gli errori conservano il form compilato; il successo mostra il ticket appena creato.
    template = "ticket_success.html" if ticket_form.get("created_ticket") else "ticket_panel.html"
    response = render(request, template, context)
    # Il client riconosce i frammenti validi ed evita di inserire pagine complete di login o diniego.
    response["X-Assistant-Form"] = "ready"
    # Il frammento può contenere dati personali o valori inseriti: non viene conservato in cache.
    response["Cache-Control"] = "no-store"
    return response
