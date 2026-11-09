"""URL di prova: aggiungono il prototipo senza sostituire le view originali."""
from django.urls import include, path
from django.views.generic import RedirectView
from .views import prototype

urlpatterns = [
    path("", RedirectView.as_view(url="/receiver-lab/", permanent=False)),
    path("receiver-lab/", prototype, name="receiver-lab"),
    path("", include("uni_ticket_project.urls")),
]
