"""Local-only settings for the receiver investigation, never for runserver."""

import atexit
from pathlib import Path
from tempfile import TemporaryDirectory

from uni_ticket_project.settings import *  # noqa: F403


_test_directory = TemporaryDirectory(prefix="uniticket-signal-test-")
atexit.register(_test_directory.cleanup)
TICKET_EVENTS_TEST_ROOT = _test_directory.name
TICKET_EVENTS_ISOLATED_TEST = True

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
        "TEST": {"NAME": ":memory:"},
    }
}

MEDIA_ROOT = str(Path(TICKET_EVENTS_TEST_ROOT) / "media")
STATIC_ROOT = str(Path(TICKET_EVENTS_TEST_ROOT) / "static")
TMP_DIR = str(Path(TICKET_EVENTS_TEST_ROOT) / "tmp")
for _directory in (MEDIA_ROOT, STATIC_ROOT, TMP_DIR):
    Path(_directory).mkdir(parents=True, exist_ok=True)

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "test_console": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
        }
    },
    "loggers": {
        "ticket_events": {
            "handlers": ["test_console"],
            "level": "INFO",
            "propagate": False,
        }
    },
}
