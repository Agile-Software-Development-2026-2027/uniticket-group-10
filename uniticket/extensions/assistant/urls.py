from django.urls import include, path

from .thread import CreateThreadView

from .api import AgentProxyView
from .catalog import AvailableCategoriesView

from .search import CategorySearchView


urlpatterns = [
    path("api/assistant", AgentProxyView.as_view(), name="assistant_agent"),
    path("api/assistant/categories/", AvailableCategoriesView.as_view(), name="assistant_categories"),
    path("api/assistant/search/", CategorySearchView.as_view(), name="assistant_search"),
    path("api/assistant/thread/new/", CreateThreadView.as_view(), name="assistant-thread-new"),
    path("", include("uni_ticket_project.urls")),
]
