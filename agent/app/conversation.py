"""Messaggi, azioni e regole della conversazione, eseguiti soltanto dall'agente."""

from gettext import translation
from pathlib import Path

from .contracts import (
    AssistantMessage, FormHelpAction, TicketSuggestion, TicketSuggestions,
)


class ConversationError(Exception):
    def __init__(self, status: int, detail: dict):
        self.status = status
        self.detail = detail


def translator(language: str):
    locale_dir = Path(__file__).resolve().parents[1] / "locale"
    return translation("messages", localedir=locale_dir, languages=[language], fallback=True).gettext


def search_tickets(state: dict) -> dict:
    request = state["request"]
    _ = translator(request.language)
    text = request.input.message.lower()
    tickets = [TicketSuggestion(category_id=category.id, title=category.name,
                                structure_name=category.structure_name, url=category.url)
               for category in request.catalog if not category.hidden and text in category.name.lower()]
    text = (_("Ecco le richieste che potrebbero fare al caso tuo. Seleziona quella che vuoi aprire.") if tickets else
            _("Non ho trovato richieste adatte. Prova a indicare il servizio o il documento di cui hai bisogno."))
    message = AssistantMessage(message=text, content=TicketSuggestions(tickets=tickets) if tickets else None)
    return {"messages": [message.to_dict()]}


def selected_category(request):
    _ = translator(request.language)
    category = next((category for category in request.catalog if category.id == request.input.category_id and not category.hidden), None)
    if category is None:
        raise ConversationError(404, {"detail": _("Domanda non trovata o scaduta.")})
    return category


def offer_help(state: dict) -> dict:
    request = state["request"]
    _ = translator(request.language)
    category = selected_category(request)
    message = AssistantMessage(
        message=_("Vuoi aiuto a compilare la richiesta «%(ticket)s»?") % {"ticket": category.name},
        action=FormHelpAction(type="request_form_help", category_id=category.id,
                              label=_("Aiutami a compilare questa richiesta")),
    )
    return {"messages": [message.to_dict()]}


def help_with_form(state: dict) -> dict:
    request = state["request"]
    _ = translator(request.language)
    selected_category(request)
    message = AssistantMessage(message=_("Ti aiuto a compilare la richiesta. Da quale campo vuoi partire?"))
    return {"messages": [message.to_dict()]}
