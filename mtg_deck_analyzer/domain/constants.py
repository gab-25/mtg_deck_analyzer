"""Shared constants used across modules."""

# Custom User-Agent required by the Scryfall API.
SCRYFALL_HEADERS = {
    "User-Agent": "MTGDeckAnalyzer/1.0.0 (contact@mtgdeckanalyzer.com; pair-programming)"
}

# Gemini model used for deck analysis.
GEMINI_MODEL = "gemini-2.5-flash"

# Selectable deck types shown in the creation form. The empty value lets the
# pipeline infer the type from the decklist (see ``infer_deck_type``).
DECK_TYPES = [
    "Commander / EDH",
    "Constructed",
    "Limited",
    "Custom",
]

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
