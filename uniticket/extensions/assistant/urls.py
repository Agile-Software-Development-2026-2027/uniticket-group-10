from django.urls import include, path

from .thread import CreateThreadView

from .api import AgentProxyView
from .catalog import AvailableCategoriesView, AvailableStructuresView

from .search import CategorySearchView
from .form_schema_api import CategoryFormSchemaView
from .form_validation_api import CategoryFormValidationView


urlpatterns = [
    path("api/assistant", AgentProxyView.as_view(), name="assistant_agent"),
    path("api/assistant/structures/", AvailableStructuresView.as_view(), name="assistant_structures"),
    path("api/assistant/categories/", AvailableCategoriesView.as_view(), name="assistant_categories"),
    path("api/assistant/categories/<int:category_id>/form-schema/", CategoryFormSchemaView.as_view(), name="assistant_form_schema"),
    path("api/assistant/categories/<int:category_id>/form-validation/", CategoryFormValidationView.as_view(), name="assistant_form_validation"),
    path("api/assistant/search/", CategorySearchView.as_view(), name="assistant_search"),
    path("api/assistant/thread/new/", CreateThreadView.as_view(), name="assistant-thread-new"),
    path("", include("uni_ticket_project.urls")),
]
