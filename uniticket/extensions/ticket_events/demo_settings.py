"""Settings exclusively for the local receiver laboratory."""
from pathlib import Path
from uni_ticket_project.settings import *  # noqa: F403

RECEIVER_DEMO = True
DEBUG = False
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
ROOT_URLCONF = "ticket_events.demo_urls"
INSTALLED_APPS = [*INSTALLED_APPS, "ticket_events.apps.TicketEventsConfig"]
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
