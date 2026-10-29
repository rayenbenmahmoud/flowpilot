"""Settings used by pytest: in-memory SQLite, inline Celery, known test secrets."""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-secret-key")
os.environ["DATABASE_URL"] = ""

from .settings import *  # noqa: E402, F403

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
CELERY_TASK_ALWAYS_EAGER = True
FLOWPILOT_DEMO_MODE = True
FLOWPILOT_WEBHOOK_SECRET = "test-webhook-secret"  # noqa: S105
FLOWPILOT_ADAPTER_MAX_ATTEMPTS = 2
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
LOGGING = {"version": 1, "disable_existing_loggers": False}
