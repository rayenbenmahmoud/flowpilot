"""FlowPilot settings.

Every secret and deployment-specific value comes from environment variables
(see ``.env.example``). Nothing sensitive is hard-coded here.
"""

import os
from pathlib import Path
from urllib.parse import unquote, urlparse

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

try:  # optional convenience for local development
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR.parent / ".env")
except ImportError:  # pragma: no cover
    pass


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError as exc:
        raise ImproperlyConfigured(f"{name} must be an integer") from exc


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


def database_from_url(url: str) -> dict:
    """SQLite when DATABASE_URL is empty (quick local run), PostgreSQL otherwise."""
    if not url:
        return {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}
    parsed = urlparse(url)
    if parsed.scheme in {"postgres", "postgresql"}:
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": parsed.path.lstrip("/"),
            "USER": unquote(parsed.username or ""),
            "PASSWORD": unquote(parsed.password or ""),
            "HOST": parsed.hostname or "localhost",
            "PORT": str(parsed.port or 5432),
            "CONN_MAX_AGE": 60,
        }
    raise ImproperlyConfigured("DATABASE_URL must be empty or a postgres:// URL")


# --- Core Django -----------------------------------------------------------
DEBUG = env_bool("DJANGO_DEBUG", False)
SECRET_KEY = env("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "insecure-development-key-never-use-in-production"  # noqa: S105
    else:
        raise ImproperlyConfigured("Set DJANGO_SECRET_KEY (see .env.example).")
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "django_filters",
    "corsheaders",
    "drf_spectacular",
    "drf_spectacular_sidecar",
    "automation",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

DATABASES = {"default": database_from_url(env("DATABASE_URL"))}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

# Browser hardening (kept on in every environment; HTTPS-only flags are opt-in).
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", False)
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
SECURE_SSL_REDIRECT = env_bool("DJANGO_SSL_REDIRECT", False)

CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")

# --- Cache (used for rate limiting). Redis when available, in-process otherwise.
REDIS_URL = env("REDIS_URL")
if REDIS_URL:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS_URL}}
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# --- REST framework / OpenAPI ----------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.TokenAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_PAGINATION_CLASS": "automation.pagination.StandardPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "automation.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_RATES": {
        "webhook": env("FLOWPILOT_WEBHOOK_RATE", "60/min"),
        "login": env("FLOWPILOT_LOGIN_RATE", "10/min"),
    },
    "NUM_PROXIES": env_int("FLOWPILOT_NUM_PROXIES", 0) or None,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "FlowPilot API",
    "DESCRIPTION": (
        "Business workflow automation API.\n\n"
        "**Dashboard API** calls use `Authorization: Token <token>` (see `/auth/login/`).\n\n"
        "**Webhook calls** are not token-authenticated. They must carry "
        "`X-FlowPilot-Timestamp` (unix seconds) and `X-FlowPilot-Signature: sha256=<hex>` where "
        'the hex value is HMAC-SHA256 of `"<timestamp>.<raw body>"` with the webhook secret, '
        "plus an `Idempotency-Key` header (or `event_id` in the body)."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "REDOC_DIST": "SIDECAR",
    "ENUM_NAME_OVERRIDES": {
        "WorkflowStatusEnum": "automation.models.Workflow.Status",
        "WritableWorkflowStatusEnum": ["active", "disabled"],
        "ExecutionStatusEnum": "automation.models.Execution.Status",
        "SeverityEnum": "automation.models.Notification.Severity",
    },
}

# --- Celery -----------------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL", "")
# Without a broker the engine runs tasks inline so the demo works with no Redis.
CELERY_TASK_ALWAYS_EAGER = env_bool("FLOWPILOT_EAGER_TASKS", not CELERY_BROKER_URL)
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TASK_TIME_LIMIT = 120

# --- Email (only used when demo mode is off) ---------------------------------
EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_TIMEOUT = env_int("EMAIL_TIMEOUT", 10)
DEFAULT_FROM_EMAIL = env("EMAIL_FROM", "FlowPilot <no-reply@example.com>")

# --- FlowPilot ---------------------------------------------------------------
FLOWPILOT_DEMO_MODE = env_bool("FLOWPILOT_DEMO_MODE", True)  # safe default: simulate everything
FLOWPILOT_WEBHOOK_SECRET = env("FLOWPILOT_WEBHOOK_SECRET")
FLOWPILOT_WEBHOOK_MAX_BYTES = env_int("FLOWPILOT_WEBHOOK_MAX_BYTES", 65536)
FLOWPILOT_WEBHOOK_TOLERANCE_SECONDS = env_int("FLOWPILOT_WEBHOOK_TOLERANCE_SECONDS", 300)
FLOWPILOT_MAX_ATTEMPTS = env_int("FLOWPILOT_MAX_ATTEMPTS", 3)
FLOWPILOT_ADAPTER_TIMEOUT = env_int("FLOWPILOT_ADAPTER_TIMEOUT", 5)
FLOWPILOT_ADAPTER_MAX_ATTEMPTS = env_int("FLOWPILOT_ADAPTER_MAX_ATTEMPTS", 2)
FLOWPILOT_N8N_BASE_URL = env("FLOWPILOT_N8N_BASE_URL")
FLOWPILOT_N8N_WEBHOOK_SECRET = env("FLOWPILOT_N8N_WEBHOOK_SECRET")
FLOWPILOT_EXTERNAL_API_BASE_URL = env("FLOWPILOT_EXTERNAL_API_BASE_URL")
FLOWPILOT_EXTERNAL_API_KEY = env("FLOWPILOT_EXTERNAL_API_KEY")
FLOWPILOT_DEMO_USER_PASSWORD = env("FLOWPILOT_DEMO_USER_PASSWORD", "flowpilot-demo")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"scrub": {"()": "automation.logging_filters.SecretScrubFilter"}},
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain", "filters": ["scrub"]}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}
