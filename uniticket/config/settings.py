# Import default settings
from uni_ticket_project.settings import *

# Overwrite default settings
ROOT_URLCONF = "assistant.urls"

# Registra i receiver senza sostituire le app configurate da UniTicket e dall'assistente.
INSTALLED_APPS = [*INSTALLED_APPS, "ticket_events.apps.TicketEventsConfig"]
