"""ASGI entry point for the MTG Deck Analyzer."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mtg_deck_analyzer.settings")

application = get_asgi_application()
