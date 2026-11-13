from django.apps import AppConfig
from django.urls import reverse
from django.db import connection
from threading import Thread
import time

def _get_strutture():
    from rest_framework.test import APIRequestFactory
    from api_rest.views.generic import TicketAPIStruttureList

    factory = APIRequestFactory()
    view = TicketAPIStruttureList.as_view(permission_classes=[])
    url = reverse("api_rest:api-strutture-list")
    strutture = []

    while url:
        response = view(factory.get(url))
        strutture.extend(response.data["results"])
        url = response.data["next"]

    return strutture

def _get_categories():
    from rest_framework.test import APIRequestFactory
    from api_rest.views.generic import TicketAPITicketCategoryList

    factory = APIRequestFactory()
    view = TicketAPITicketCategoryList.as_view(permission_classes=[])
    url = reverse("api_rest:api-ticket-category-list")
    categories = []

    while url:
        response = view(factory.get(url))
        categories.extend(response.data["results"])
        url = response.data["next"]

    return categories

# WARNING: this is an accrocco.
def _wait_db():
    while True:
        try:
            tables = connection.introspection.table_names()

            required_tables = [
                "uni_ticket_ticketcategory",
            ]

            if all(table in tables for table in required_tables):
                break

        except Exception:
            pass

        time.sleep(3)

class InitialIndexingConfig(AppConfig):
    name = "initial_indexing"
    verbose_name = "Initial ticket indexing"

    has_strutture = False
    has_categories = False

    def ready(self):
        Thread(target=self.initial_indexing, daemon=True).start()

    def initial_indexing(self):
        _wait_db()

        if not self.has_strutture:
            strutture = _get_strutture()

            if len(strutture) > 0:
                pass # What to do here?

            self.has_strutture = True

        if not self.has_categories:
            categories = _get_categories()

            if len(categories) > 0:
                for category in categories:
                    from ticket_events import orchestrator
                    orchestrator.upsert_category(category["id"])

                self.has_categories = True