"""Shared constants used across modules."""

# Custom User-Agent required by the Scryfall API.
SCRYFALL_HEADERS = {
    "User-Agent": "MTGDeckAnalyzer/1.0.0 (contact@mtgdeckanalyzer.com; pair-programming)"
}

# Gemini model used for deck analysis.
GEMINI_MODEL = "gemini-2.5-flash"

# The one format this app supports. Every deck is analyzed, validated and
# rendered as a Commander (EDH) deck.
DECK_FORMAT = "Commander"

# Commander deck-construction rules (Comprehensive Rules 903).
# A deck is exactly 100 cards, commander(s) included.
COMMANDER_DECK_SIZE = 100
# One commander, or two when they have partner / a background.
MAX_COMMANDERS = 2

# Cards whose rules text lifts the singleton restriction (Relentless Rats,
# Shadowborn Apostle, Persistent Petitioners, Dragon's Approach, ...).
UNLIMITED_COPIES_TEXT = "a deck can have any number of cards named"

# The singleton rule is checked twice: once on the pasted decklist, where only
# card *names* are known, and once on the fetched cards, where the rules text
# above settles it. These two lists back the by-name pass.
BASIC_LAND_NAMES = frozenset(
    name.lower()
    for base in ("Plains", "Island", "Swamp", "Mountain", "Forest")
    for name in (base, f"Snow-Covered {base}")
) | {"wastes", "snow-covered wastes"}

# Cards printed with "A deck can have any number of cards named ...". A finite,
# hand-maintained list: it only has to cover the by-name pass, since the fetched
# card's rules text is authoritative afterwards. The few cards that cap the
# allowance (Seven Dwarves, Nazgûl) are treated as unlimited — the cap is not
# enforced.
ANY_NUMBER_CARD_NAMES = frozenset(
    name.lower()
    for name in (
        "Relentless Rats",
        "Rat Colony",
        "Shadowborn Apostle",
        "Persistent Petitioners",
        "Dragon's Approach",
        "Slime Against Humanity",
        "Seven Dwarves",
        "Nazgûl",
    )
)

# Rules text that lets a non-legendary-creature card be a commander
# (planeswalkers such as Rowan, Scion of War; backgrounds; etc.).
CAN_BE_COMMANDER_TEXT = "can be your commander"

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
