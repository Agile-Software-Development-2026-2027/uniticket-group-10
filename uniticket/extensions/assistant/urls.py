from django.urls import include, path

from .thread import CreateThreadView

from .api import AgentProxyView
from .catalog import AvailableCategoriesView, AvailableStructuresView


urlpatterns = [
    path("api/assistant", AgentProxyView.as_view(), name="assistant_agent"),
    path("api/assistant/structures/", AvailableStructuresView.as_view(), name="assistant_structures"),
    path("api/assistant/categories/", AvailableCategoriesView.as_view(), name="assistant_categories"),
    path("api/assistant/thread/new/", CreateThreadView.as_view(), name="assistant-thread-new"),
    path("", include("uni_ticket_project.urls")),
]
