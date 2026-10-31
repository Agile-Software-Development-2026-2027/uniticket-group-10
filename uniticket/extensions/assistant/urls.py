from django.urls import include, path
from .api import search

from .views import demo_page


urlpatterns = [
    path("api/search", search, name="assistant_search"), # esegue la post (la nostra api finta per ora)
    path("assistant", demo_page.workspace, name="assistant_workspace"), # demo a pagina intera
    path("assistant/<int:ticket_id>", demo_page.workspace, name="assistant_workspace_category"),
    path("", include("uni_ticket_project.urls")), # includes also urls originally present in uniticket, think as this is an "extension"
]
