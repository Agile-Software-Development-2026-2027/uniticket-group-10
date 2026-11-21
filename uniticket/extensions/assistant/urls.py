from django.urls import include, path

from .thread import CreateThreadView

from .api import AgentProxyView
from .catalog import AvailableCategoriesView, AvailableStructuresView

from .search import CategorySearchView

from .context import SetContextView

urlpatterns = [
    path("api/assistant", AgentProxyView.as_view(), name="assistant_agent"),
    path("api/assistant/structures/", AvailableStructuresView.as_view(), name="assistant_structures"),
    path("api/assistant/categories/", AvailableCategoriesView.as_view(), name="assistant_categories"),
    path("api/assistant/search/", CategorySearchView.as_view(), name="assistant_search"),
    path("api/assistant/thread/new/", CreateThreadView.as_view(), name="assistant-thread-new"),
    path("api/assistant/context", SetContextView.as_view(), name="assistant-set-context"),
    path("", include("uni_ticket_project.urls")),
]
