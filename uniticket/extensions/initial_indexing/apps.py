from django.apps import AppConfig
from django.urls import reverse
from django.db import connection
from threading import Thread
import time

def _get_categories():
    from uni_ticket.models import TicketCategory

    return list(TicketCategory.objects.all().values())

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

    has_categories = False

    def ready(self):
        Thread(target=self.initial_indexing, daemon=True).start()

    def initial_indexing(self):
        _wait_db()

        if not self.has_categories:
            categories = _get_categories()

            if len(categories) > 0:
                for category in categories:
                    from ticket_events import orchestrator
                    orchestrator.upsert_category(category["id"])

                self.has_categories = True