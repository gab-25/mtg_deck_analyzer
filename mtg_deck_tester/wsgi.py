"""WSGI entry point (gunicorn in the Docker image)."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mtg_deck_tester.settings")

application = get_wsgi_application()
