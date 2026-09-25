"""The Commander formats a deck can be built for and a match can be played in."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Format:
    """Everything that varies between the supported Commander formats.

    Deck construction does not vary — 100 cards, singleton, one commander — so
    those rules live in :mod:`decks.rules.commander`. What varies is the ban
    list a deck is checked against and the game it is played in.
    """

    label: str
    # Key read inside a card's Scryfall ``legalities`` dict.
    legality_key: str
    starting_life: int
    # How many players sit at a table of this format.
    min_seats: int
    max_seats: int
    # Combat damage from a single commander that eliminates a player, or None
    # when the format does not track commander damage.
    commander_damage_limit: int | None


FORMATS: dict[str, Format] = {
    "commander": Format(
        label="Commander",
        legality_key="commander",
        starting_life=40,
        min_seats=2,
        max_seats=4,
        commander_damage_limit=21,
    ),
    "duel": Format(
        label="Duel Commander",
        legality_key="duel",
        starting_life=20,
        min_seats=2,
        max_seats=2,
        commander_damage_limit=None,
    ),
}

DEFAULT_FORMAT = "commander"


def format_choices() -> list[tuple[str, str]]:
    """The ``FORMATS`` registry as Django model/form choices."""
    return [(key, fmt.label) for key, fmt in FORMATS.items()]
