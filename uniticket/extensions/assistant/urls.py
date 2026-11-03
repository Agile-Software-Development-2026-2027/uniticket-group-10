from django.urls import include, path

from .api import ConversationView


urlpatterns = [
    path("api/conversation", ConversationView.as_view(), name="assistant_conversation"), # <--- a questo endpoint verranno inviati tutti gli eventi tra l'assistente e l'utente
    path("", include("uni_ticket_project.urls")),
]
