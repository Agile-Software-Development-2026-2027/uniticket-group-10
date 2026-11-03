from django.urls import path
from . import demo_views
urlpatterns = [
    path("", demo_views.home),
    path("api/categories/", demo_views.categories),
    path("api/categories/<int:pk>/", demo_views.category_detail),
    path("api/context/", demo_views.context),
    path("api/offices/", demo_views.offices),
    path("api/offices/<int:pk>/", demo_views.office_detail),
]
