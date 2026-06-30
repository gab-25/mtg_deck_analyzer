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
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "mtg_deck_analyzer",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
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

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

STATIC_URL = "static/"

USE_TZ = True
TIME_ZONE = "UTC"
LANGUAGE_CODE = "en-us"
