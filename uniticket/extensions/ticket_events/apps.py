from django.apps import AppConfig


class TicketEventsConfig(AppConfig):
    name = "ticket_events"
    verbose_name = "Ticket definition event investigation"

    def ready(self):
        from . import signals  # noqa: F401
