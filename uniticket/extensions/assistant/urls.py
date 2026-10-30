from django.urls import include, path

from .api import search
from .views import workspace


urlpatterns = [
    path("api/search", search, name="assistant_search"),
    path("assistant", workspace, name="assistant_workspace"),
    path("", include("uni_ticket_project.urls")), # includes also urls originally present in uniticket, think as this is an "extension"
]
