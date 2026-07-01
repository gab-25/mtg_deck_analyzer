"""Shared constants used across modules."""

# Custom User-Agent required by the Scryfall API.
SCRYFALL_HEADERS = {
    "User-Agent": "MTGDeckAnalyzer/1.0.0 (contact@mtgdeckanalyzer.com; pair-programming)"
}

# Gemini model used for translations and analysis.
GEMINI_MODEL = "gemini-2.5-flash"

# Single source of truth for the supported card languages.
#   display_name: shown in the UI (the language's own name)
#   gemini_name:  the English language name used inside Gemini prompts
# Card names/descriptions are localized from Scryfall in these languages, with a
# Gemini machine-translation fallback when no official localized text exists.
LANGUAGES = {
    "en": {"display_name": "English", "gemini_name": "English"},
    "it": {"display_name": "Italiano", "gemini_name": "Italian"},
    "es": {"display_name": "Español", "gemini_name": "Spanish"},
    "fr": {"display_name": "Français", "gemini_name": "French"},
    "de": {"display_name": "Deutsch", "gemini_name": "German"},
}

DEFAULT_LANG = "en"

# Selectable deck types shown in the creation form. The empty value lets the
# pipeline infer the type from the decklist (see ``infer_deck_type``).
DECK_TYPES = [
    "Commander / EDH",
    "Constructed",
    "Limited",
    "Custom",
]

# Derived views kept for convenience and backward compatibility.
LANG_MAP = {code: meta["gemini_name"] for code, meta in LANGUAGES.items()}
LANG_DISPLAY_NAMES = {code: meta["display_name"] for code, meta in LANGUAGES.items()}


def normalize_lang(code: str) -> str:
    """Lowercases a language code and validates it against the registry.

    Unknown or empty codes fall back to :data:`DEFAULT_LANG`.
    """
    code = (code or "").lower()
    return code if code in LANGUAGES else DEFAULT_LANG

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
