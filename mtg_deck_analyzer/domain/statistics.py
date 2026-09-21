"""The deck statistics panel, assembled once and read by both renderers.

One pure function over the processed cards. Everything it needs is already in
the cached Scryfall JSON: no network, no model call, no new dependency — which
is also why the result can simply be stored with the deck.
"""

from decimal import Decimal, ROUND_HALF_UP

from .cards import classify_card
from .commander import WUBRG
from .mana import (
    CURVE_BUCKETS,
    CURVE_LABELS,
    OPENING_HAND_SIZE,
    cards_seen,
    color_card_counts,
    color_curves,
    is_land_card,
    deck_pips,
    land_production,
    mana_curve,
    mana_value_summary,
)
from .probability import at_least, exactly

# Bumped whenever the stored dictionary changes shape. A deck whose blob
# carries a different value is stale and gets recomputed rather than read.
STATISTICS_SCHEMA = 7

# Colourless is a production column only — it has no colour identity and no
# coloured pips, so it sits after WUBRG with two of its four figures at zero.
COLOR_KEYS = list(WUBRG) + ["C"]

# Land counts a seven-card hand is reported for, and the window that makes a
# hand keepable without thinking about it.
# The whole distribution, not just the keepable slice: how often a hand
# falls *outside* the window is the figure a mulligan decision turns on.
HAND_LAND_COUNTS = tuple(range(OPENING_HAND_SIZE + 1))
KEEPABLE_LANDS = (2, 3, 4, 5)
# Turns the land-drop table covers, on the play.
LAND_DROP_TURNS = (1, 2, 3, 4, 5)


def _library(processed_cards: list) -> list:
    """The cards that can actually be drawn: everything but the commander."""
    return [item for item in processed_cards if not item.get("is_commander")]


def _quantity(items: list) -> int:
    return sum(item["quantity"] for item in items)


def curve_bars(curve: list) -> list:
    """Curve entries with each bucket's total and its height as a percentage.

    Presentation, so it is not stored — but it lives here rather than twice
    over in the view and the PDF.
    """
    totals = [entry["permanents"] + entry["spells"] for entry in curve]
    peak = max(totals, default=0) or 1
    return [
        {**entry, "total": total, "pct": round(total / peak * 100)}
        for entry, total in zip(curve, totals)
    ]


def _opening_hand(library_size: int, land_count: int) -> dict:
    """Opening-hand and early-turn odds, computed rather than simulated.

    Counted over the library rather than the deck: these are odds of *drawing*
    a card, and the commander is never drawn.
    """
    return {
        "hand_size": OPENING_HAND_SIZE,
        # The expected number of lands in seven cards. Closed form rather than
        # a sum over the distribution: the two agree, and this one survives a
        # deck too small to draw a full hand from.
        "average_lands": (
            OPENING_HAND_SIZE * land_count / library_size if library_size else 0.0
        ),
        # Exactly k lands in the opening seven, for every k.
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
    }


def _pct(part: int, whole: int) -> int:
    """A share as a whole percentage; an empty whole is simply zero.

    Ties round up rather than to even. Python's round() would turn 12.5 into
    12, which surprises anyone reading a percentage — and was the last figure
    on which this disagreed with Moxfield's published numbers.
    """
    if not whole:
        return 0
    share = Decimal(part) * 100 / Decimal(whole)
    return int(share.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _colors_block(processed_cards: list) -> list:
    """The six colour columns: card share, symbol share, production, curve."""
    cards = color_card_counts(processed_cards)
    pips = deck_pips(processed_cards)
    curves = color_curves(processed_cards)
    lands = land_production(processed_cards)
    total_pips = sum(pips.values())

    return [
        {
            "key": color,
            "card_pct": _pct(cards["by_color"].get(color, 0), cards["non_lands"]),
            "symbol_pct": _pct(pips.get(color, 0), total_pips),
            "production_pct": _pct(lands["by_color"][color], lands["lands"]),
            "lands_pct": _pct(lands["by_color"][color], lands["symbol_slots"]),
            "curve": curves.get(color, [0] * CURVE_BUCKETS),
        }
        for color in COLOR_KEYS
    ]


def deck_statistics(processed_cards: list) -> dict:
    """Everything the statistics panel shows, derived from the cards alone.

    Mirrors the blocks Moxfield's deck page shows, in its order: the curve,
    the mana-value sentence, the colour columns, and the opening hand.
    """
    library = _library(processed_cards)
    library_size = _quantity(library)
    # The any-face rule, not classify_card's front face: a modal card with a
    # land back is a land you can draw and play, so it belongs in every figure
    # about lands in hand. Moxfield's published average for a real deck only
    # reconciles this way — 23 lands over 98 cards gives their 1.64, the
    # front-face count of 21 gives 1.50. The curve and the mana-value sentence
    # keep the front-face rule, because there the question is what the card is
    # cast as.
    land_count = _quantity([item for item in library if is_land_card(item["data"])])

    return {
        "schema": STATISTICS_SCHEMA,
        "library_size": library_size,
        "land_count": land_count,
        # Decks analyzed before produced_mana was carried through cannot report
        # what their lands tap for; saying "0%" would read as a broken mana base
        # rather than as missing data.
        "sources_known": any(
            "produced_mana" in item["data"] for item in processed_cards
        ),
        "curve": [
            {"label": label, **bucket}
            for label, bucket in zip(CURVE_LABELS, mana_curve(processed_cards))
        ],
        "mana_values": mana_value_summary(processed_cards),
        "colors": _colors_block(processed_cards),
        "opening_hand": _opening_hand(library_size, land_count),
    }
