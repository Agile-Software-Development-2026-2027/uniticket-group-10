from django.urls import include, path

from .views import workspace


urlpatterns = [
    path("assistant", workspace, name="assistant_workspace"),
    path("", include("uni_ticket_project.urls")), # includes also urls originally present in uniticket, think as this is an "extension"
]
