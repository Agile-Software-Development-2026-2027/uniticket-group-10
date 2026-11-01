from django.urls import include, path

from .api import search
from .views import ticket_form, workspace


urlpatterns = [
    # Ricerca della chat: POST JSON, distinta dalle risposte HTML dei moduli.
    path("api/search", search, name="assistant_search"),
    # GET carica il pannello; POST restituisce errori di validazione o conferma di creazione.
    path("assistant/form", ticket_form, name="assistant_ticket_form"),
    # Pagina completa, accesso diretto con ticket_id e percorso di invio alternativo.
    path("assistant", workspace, name="assistant_workspace"),
    path("", include("uni_ticket_project.urls")), # Mantiene raggiungibili le route originali di UniTicket.
]
