"""Template del prototipo con database e allegati temporanei dei test."""
from copy import deepcopy
from pathlib import Path
from ticket_events.test_settings import *  # noqa: F403

TEMPLATES = deepcopy(TEMPLATES)  # noqa: F405
TEMPLATES[0]["DIRS"].insert(0, str(Path(__file__).parent / "templates"))
# I comandi del laboratorio restano disponibili soltanto ai suoi test.
INSTALLED_APPS = [*INSTALLED_APPS, "receiver_lab"]  # noqa: F405
