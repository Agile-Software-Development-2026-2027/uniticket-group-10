from django.apps import AppConfig


class TicketEventsConfig(AppConfig):
    name = "ticket_events"
    verbose_name = "Ticket definition events"

    def ready(self):
        # Unico punto di registrazione dei receiver, valido anche per le view originali.
        from . import signals  # noqa: F401
