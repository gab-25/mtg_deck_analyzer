"""Django settings for the MTG Deck Analyzer web service.

Configuration comes from environment variables (loaded from a ``.env`` file in
local development — see ``__init__.py``). The database connection string is the
``DATABASE_URL`` variable and accepts the same SQLAlchemy-style URLs the project
used before (``postgresql+psycopg://…`` / ``sqlite+pysqlite:///…``); the driver
suffix is ignored.
"""

import os
import urllib.parse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-key-change-me")
DEBUG = os.environ.get("DEBUG", "1").lower() in {"1", "true", "yes"}
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "tailwind",
    "theme",
    "django_htmx",
    "mtg_deck_analyzer",
]

TAILWIND_APP_NAME = "theme"

# Use the standalone Tailwind CLI binary (via pytailwindcss) so neither the dev
# environment nor the Docker image needs a Node.js toolchain.
TAILWIND_USE_STANDALONE_BINARY = True

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise serves the collected static files directly from the app server
    # (no separate web server needed); must sit right after SecurityMiddleware.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Populates ``request.htmx`` from the HX-* request headers.
    "django_htmx.middleware.HtmxMiddleware",
]

ROOT_URLCONF = "mtg_deck_analyzer.urls"

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
                "mtg_deck_analyzer.context_processors.app_version",
            ],
        },
    },
]

WSGI_APPLICATION = "mtg_deck_analyzer.wsgi.application"
ASGI_APPLICATION = "mtg_deck_analyzer.asgi.application"

DEFAULT_DATABASE_URL = "postgresql+psycopg://mtg:mtg@localhost:5432/mtg"


def _database_config(url: str) -> dict:
    """Builds a Django ``DATABASES['default']`` entry from a connection URL.

    Accepts the SQLAlchemy-style URLs the project historically used: any
    ``+driver`` suffix on the scheme (e.g. ``+psycopg``, ``+pysqlite``) is
    stripped, since Django picks the driver from the backend itself.
    """
    parsed = urllib.parse.urlparse(url)
    scheme = parsed.scheme.split("+", 1)[0]

    if scheme == "sqlite":
        # ``sqlite:///./mtg.db`` -> ``./mtg.db``; ``sqlite:///:memory:`` -> ``:memory:``.
        name = (parsed.netloc + parsed.path).lstrip("/")
        return {"ENGINE": "django.db.backends.sqlite3", "NAME": name or ":memory:"}

    if scheme in {"postgres", "postgresql"}:
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": parsed.path.lstrip("/"),
            "USER": urllib.parse.unquote(parsed.username or ""),
            "PASSWORD": urllib.parse.unquote(parsed.password or ""),
            "HOST": parsed.hostname or "",
            "PORT": str(parsed.port or ""),
        }

    raise ValueError(f"Unsupported DATABASE_URL scheme: {parsed.scheme!r}")


DATABASES = {
    "default": _database_config(
        os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Authentication: log-in gates the whole app; both views below are named routes.
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "index"
LOGOUT_REDIRECT_URL = "login"

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# In production (DEBUG off) WhiteNoise serves compressed, hash-versioned static
# files from STATIC_ROOT. In development the plain finder-based storage is used
# so the app works without running ``collectstatic`` first.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}

USE_TZ = True
USE_I18N = True
TIME_ZONE = "UTC"
LANGUAGE_CODE = "en-us"

# Run the (multi-minute) Scryfall + Gemini deck analysis in a background thread
# so the create request returns immediately. Disabled in tests, where the work
# must run inline for deterministic assertions (see ``settings_test``).
ASYNC_DECK_ANALYSIS = os.environ.get("ASYNC_DECK_ANALYSIS", "1").lower() in {
    "1",
    "true",
    "yes",
}

# Surface application logs (including the background deck-analysis progress) on
# the console. Level is controlled by ``LOG_LEVEL`` (defaults to INFO).
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "deck_id": {
            "()": "mtg_deck_analyzer.logging_context.DeckIdFilter",
        },
    },
    "formatters": {
        "simple": {
            "format": "{asctime} {levelname} {name}: {deck_id}{message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
            "filters": ["deck_id"],
        },
    },
    "loggers": {
        "mtg_deck_analyzer": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
    },
}
