"""Shared constants used across modules."""

from dataclasses import dataclass

# Custom User-Agent required by the Scryfall API.
SCRYFALL_HEADERS = {
    "User-Agent": "MTGDeckAnalyzer/1.0.0 (contact@mtgdeckanalyzer.com; pair-programming)"
}

# Default model used for deck analysis, as an OpenRouter model id (any model
# listed on https://openrouter.ai/models works). Override it at runtime with
# the OPENROUTER_MODEL environment variable, no code change needed.
OPENROUTER_MODEL = "google/gemini-2.5-flash"

# Commander deck-construction rules (Comprehensive Rules 903).
# A deck is exactly 100 cards, commander included.
COMMANDER_DECK_SIZE = 100
# A single commander. The official rules also allow two with partner or a
# background; this app deliberately does not.
MAX_COMMANDERS = 1

@dataclass(frozen=True)
class Format:
    """Everything that varies between the Commander formats this app supports.

    Deck construction does not vary — 100 cards, singleton, one commander — so
    the size and commander-count rules above stay global. What varies is the
    ban list to check against and the game the deck is actually played in,
    which the AI analysis has to know about to give useful advice.
    """

    label: str
    # Key read inside a card's Scryfall ``legalities`` dict.
    legality_key: str
    # Starting life total and a one-line description of the game; both are
    # interpolated into the analysis prompt.
    life: int
    context: str


FORMATS: dict[str, Format] = {
    "commander": Format(
        label="Commander",
        legality_key="commander",
        life=40,
        context=(
            "multiplayer (typically a four-player pod), where politics and "
            "threat assessment matter"
        ),
    ),
    "duel": Format(
        label="Duel Commander",
        legality_key="duel",
        life=20,
        context=(
            "a 1v1 duel, with no politics, a much faster clock and a heavier "
            "premium on efficient interaction"
        ),
    ),
}

# The format a deck is assumed to be when nothing says otherwise: every deck
# stored before the format was a choice is a Commander deck.
DEFAULT_FORMAT = "commander"


def format_choices() -> list[tuple[str, str]]:
    """The ``FORMATS`` registry as Django model/form choices."""
    return [(key, fmt.label) for key, fmt in FORMATS.items()]


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
