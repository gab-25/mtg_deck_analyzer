"""The deck statistics panel, assembled once and read by both renderers.

One pure function over the processed cards. Everything it needs is already in
the cached Scryfall JSON: no network, no model call, no new dependency — which
is also why the result can simply be stored with the deck.
"""

from .cards import classify_card
from .constants import ROLE_LABELS, ROLE_ORDER
from .mana import (
    CURVE_LABELS,
    OPENING_HAND_SIZE,
    cards_seen,
    color_fixing,
    deck_pips,
    deck_sources,
    mana_curve,
)
from .probability import at_least, exactly
from .roles import baseline_report, role_counts

# Land counts a seven-card hand is reported for, and the window that makes a
# hand keepable without thinking about it.
HAND_LAND_COUNTS = (2, 3, 4, 5)
KEEPABLE_LANDS = (2, 3, 4, 5)
# Turns the land-drop and role tables cover, on the play.
LAND_DROP_TURNS = (1, 2, 3, 4, 5)
ROLE_TURNS = (1, 3, 5)


def _library(processed_cards: list) -> list:
    """The cards that can actually be drawn: everything but the commander."""
    return [item for item in processed_cards if not item.get("is_commander")]


def _quantity(items: list) -> int:
    return sum(item["quantity"] for item in items)


def curve_bars(curve: list) -> list:
    """Curve entries with a bar height, as a percentage of the tallest bucket.

    Presentation, so it is not stored — but it lives here rather than twice
    over in the view and the PDF.
    """
    peak = max((entry["count"] for entry in curve), default=0) or 1
    return [
        {**entry, "pct": round(entry["count"] / peak * 100)} for entry in curve
    ]


def _opening_hand(library: list, library_size: int, land_count: int) -> dict:
    """Opening-hand and early-turn odds, computed rather than simulated.

    Counted over the library rather than the deck: these are odds of *drawing*
    a card, and the commander is never drawn. So a commander that happens to
    ramp does not show up here, though it does in the deck's role counts.
    """
    counts = role_counts(library)

    return {
        "hand_size": OPENING_HAND_SIZE,
        # Exactly k lands in the opening seven.
        "land_counts": [
            {
                "lands": k,
                "p": exactly(library_size, land_count, OPENING_HAND_SIZE, k),
            }
            for k in HAND_LAND_COUNTS
        ],
        # A hand nobody has to think about: two to five lands.
        "keepable": sum(
            exactly(library_size, land_count, OPENING_HAND_SIZE, k)
            for k in KEEPABLE_LANDS
        ),
        # Hitting every land drop through turn N means holding N lands by then.
        "land_drops": [
            {
                "turn": turn,
                "p": at_least(library_size, land_count, cards_seen(turn), turn),
            }
            for turn in LAND_DROP_TURNS
        ],
        # At least one card of each role by turn N.
        "roles": [
            {
                "key": role,
                "label": ROLE_LABELS[role],
                "count": counts[role],
                "odds": [
                    {
                        "turn": turn,
                        "p": at_least(
                            library_size, counts[role], cards_seen(turn), 1
                        ),
                    }
                    for turn in ROLE_TURNS
                ],
            }
            for role in ROLE_ORDER
        ],
    }


def deck_statistics(processed_cards: list) -> dict:
    """Everything the statistics panel shows, derived from the cards alone.

    Pure and cheap, so it is computed once at analysis time and stored — and
    can be recomputed on the fly for a deck analyzed before it existed.
    """
    library = _library(processed_cards)
    library_size = _quantity(library)
    land_count = _quantity(
        [item for item in library if classify_card(item["data"]) == "Land"]
    )
    counts = role_counts(processed_cards)

    return {
        "library_size": library_size,
        "land_count": land_count,
        "curve": [
            {"label": label, "count": count}
            for label, count in zip(CURVE_LABELS, mana_curve(processed_cards))
        ],
        "pips": deck_pips(processed_cards),
        "sources": deck_sources(processed_cards),
        # Decks analyzed before produced_mana was stored cannot report sources;
        # the panel says so rather than claiming the deck has none.
        "sources_known": any(
            "produced_mana" in item["data"] for item in processed_cards
        ),
        "fixing": color_fixing(processed_cards, library_size),
        "roles": [
            {"key": role, "label": ROLE_LABELS[role], "count": counts[role]}
            for role in ROLE_ORDER
        ],
        "baseline": baseline_report(processed_cards),
        "opening_hand": _opening_hand(library, library_size, land_count),
    }
