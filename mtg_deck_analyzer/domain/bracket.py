"""Commander Bracket (1-5) estimation from the deck list alone.

Mirrors the method Moxfield documents: three list-based signals — Game
Changers, mass land denial and chained extra turns — checked against the
official bracket guidance. Combos, tutor density and how fast the deck wins
are deliberately not estimated: a list of 100 cards does not settle them, and
a confident wrong verdict is worse than a narrow right one.

The estimate is therefore a *minimum*: it says which tier the deck's contents
already require, not how the deck actually plays.
"""

from dataclasses import dataclass

from .constants import (
    BRACKET_LABELS,
    EXTRA_TURN_TEXT,
    GAME_CHANGER_NAMES,
    MASS_LAND_DENIAL_NAMES,
)
from .text_utils import front_face_name

# Two or more extra-turn cards is the "chaining" pattern the guidance pushes
# to bracket 4. A single Time Warp is not.
EXTRA_TURN_CHAIN_THRESHOLD = 2


@dataclass(frozen=True)
class BracketRule:
    """What one tier tolerates. ``max_game_changers`` None means no limit."""

    bracket: int
    max_game_changers: int | None
    allows_mass_land_denial: bool
    allows_extra_turn_chain: bool


# Read top down: a deck takes the first tier whose every limit holds. The
# table is the thing that gets edited when the Commander Format Panel revises
# the guidance, which is why it is data and not nested ifs.
#
# Bracket 1 (Exhibition, "wins are incidental") and bracket 5 (cEDH,
# tournament and metagame driven) are statements of intent rather than
# properties of a list, so the estimate floors at 2 and caps at 4.
BRACKET_RULES = [
    BracketRule(2, 0, False, False),
    BracketRule(3, 3, False, False),
    BracketRule(4, None, True, True),
]


def _name_key(card: dict) -> str:
    """The lookup key for the name lists: lowercase front face."""
    return front_face_name(card.get("name", "")).lower()


def _is_game_changer(card: dict) -> bool:
    """True when Scryfall flags the card, or the fallback list names it.

    A card cached before this app carried the flag has no key at all, and only
    then does the hand-maintained list get a say: an explicit ``False`` is
    live data and outranks a list that may have gone stale.
    """
    if "game_changer" in card:
        return bool(card["game_changer"])
    return _name_key(card) in GAME_CHANGER_NAMES


def _grants_extra_turn(card: dict) -> bool:
    """True when any face's oracle text hands out an extra turn."""
    return any(
        EXTRA_TURN_TEXT in (face.get("rules_text") or "").lower()
        for face in card.get("faces", [])
    )


def estimate_bracket(processed_cards: list) -> dict:
    """Estimates the minimum Commander Bracket for a processed deck.

    Returns the tier, its official label and the card names behind each
    signal — the names, not just the counts, so a player can argue with the
    verdict instead of having to trust it.
    """
    game_changers = []
    mass_land_denial = []
    extra_turns = []

    for item in processed_cards:
        card = item.get("data", {})
        name = card.get("name", "")
        if _is_game_changer(card):
            game_changers.append(name)
        if _name_key(card) in MASS_LAND_DENIAL_NAMES:
            mass_land_denial.append(name)
        if _grants_extra_turn(card):
            extra_turns.append(name)

    chains_turns = len(extra_turns) >= EXTRA_TURN_CHAIN_THRESHOLD

    bracket = BRACKET_RULES[-1].bracket
    for rule in BRACKET_RULES:
        if (
            rule.max_game_changers is not None
            and len(game_changers) > rule.max_game_changers
        ):
            continue
        if mass_land_denial and not rule.allows_mass_land_denial:
            continue
        if chains_turns and not rule.allows_extra_turn_chain:
            continue
        bracket = rule.bracket
        break

    return {
        "bracket": bracket,
        "label": BRACKET_LABELS[bracket],
        "signals": {
            "game_changers": sorted(game_changers),
            "mass_land_denial": sorted(mass_land_denial),
            "extra_turns": sorted(extra_turns),
        },
    }
