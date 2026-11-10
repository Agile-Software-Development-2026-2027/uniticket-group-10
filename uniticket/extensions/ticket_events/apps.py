from django.apps import AppConfig


class TicketEventsConfig(AppConfig):
    name = "ticket_events"
    verbose_name = "Ticket definition events"

    # Registra i receiver quando Django ha caricato i modelli.
    def ready(self):
        # L’import esegue i decorator @receiver presenti nel file.
        from . import signals  # noqa: F401
