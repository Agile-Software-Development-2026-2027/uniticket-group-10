"""Configurazione del solo prototipo: database, file e accesso locali."""
from copy import deepcopy
from pathlib import Path
from uni_ticket_project.settings import *  # noqa: F403

RECEIVER_DEMO = True
# Il server locale deve servire anche gli asset dell’interfaccia originale.
DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
DATABASES = {"default": {
    "ENGINE": "django.db.backends.sqlite3",
    "NAME": "/sandbox/receiver-demo.sqlite3",
    "TEST": {"NAME": ":memory:"},
}}
MEDIA_ROOT = "/sandbox/media"
STATIC_ROOT = "/sandbox/static"
TMP_DIR = "/sandbox/tmp"
for directory in (MEDIA_ROOT, STATIC_ROOT, TMP_DIR):
    Path(directory).mkdir(parents=True, exist_ok=True)
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
LOGGING = {
    "version": 1, "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler", "stream": "ext://sys.stdout"}},
    "loggers": {"ticket_events": {"handlers": ["console"], "level": "INFO", "propagate": False}},
}

# Registra soltanto nel prototipo il comando di preparazione e i template della UI.
INSTALLED_APPS = [*INSTALLED_APPS, "receiver_lab"]  # noqa: F405
ROOT_URLCONF = "receiver_lab.urls"
TEMPLATES = deepcopy(TEMPLATES)  # noqa: F405
TEMPLATES[0]["DIRS"].insert(0, str(Path(__file__).parent / "templates"))
