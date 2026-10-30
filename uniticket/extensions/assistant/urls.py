from django.urls import include, path
from .api import search

from .views import workspace,open_category


urlpatterns = [
    path("api/search", search, name="assistant_search"), # esegue la post (la nostra api finta per ora)
    path("assistant/open", open_category, name="assistant_open"), # apre il modulo per la categoria selezionata
    path("assistant", workspace, name="assistant_workspace"), # POC di Angelo
    path("", include("uni_ticket_project.urls")), # includes also urls originally present in uniticket, think as this is an "extension"
]
