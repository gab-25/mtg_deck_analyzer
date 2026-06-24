"""Shared constants used across modules."""

# Custom User-Agent required by the Scryfall API.
SCRYFALL_HEADERS = {
    "User-Agent": "MTGDeckAnalyzer/1.0.0 (contact@mtgdeckanalyzer.com; pair-programming)"
}

# Gemini model used for translations and analysis.
GEMINI_MODEL = "gemini-2.5-flash"

# Maps language codes to the name used in Gemini prompts.
LANG_MAP = {
    "en": "English",
    "it": "Italian",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
    "ja": "Japanese",
    "ko": "Korean",
    "ru": "Russian",
    "zhs": "Simplified Chinese",
    "zht": "Traditional Chinese",
}

# Language display names shown in the PDF.
LANG_DISPLAY_NAMES = {
    "it": "Italiano",
    "en": "English",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
}

# Display order of card categories.
CATEGORY_ORDER = [
    "Creature",
    "Planeswalker",
    "Artifact",
    "Enchantment",
    "Instant",
    "Sorcery",
    "Battle",
    "Land",
    "Other",
]
