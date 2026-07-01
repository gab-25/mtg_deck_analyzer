"""Django application configuration."""

from django.apps import AppConfig


class MtgDeckAnalyzerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "mtg_deck_analyzer"
    verbose_name = "MTG Deck Analyzer"
