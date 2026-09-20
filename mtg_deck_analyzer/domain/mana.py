"""What the deck asks for in colored mana, and what it offers.

Pure functions over the processed cards. Three counts read straight off the
cards: the pips a deck's costs demand, the sources that can pay them and the
mana curve.
"""

import re

from .cards import classify_card, front_type_line
from .commander import WUBRG

_MANA_SYMBOL_RE = re.compile(r"\{([^}]+)\}")

# 0..6 are exact mana values; index 7 is the merged "7 or more" bucket.
CURVE_BUCKETS = 8
CURVE_LABELS = ("0", "1", "2", "3", "4", "5", "6", "7+")

# Permanent types that can sit on the battlefield and be tapped for mana. An
# instant or sorcery that makes mana (Dark Ritual) is a one-shot, not a source.
_SOURCE_TYPES = ("land", "artifact", "creature", "enchantment", "planeswalker")


def _empty_counts() -> dict:
    return {color: 0 for color in WUBRG}


def _type_lines(card_data: dict) -> list:
    """Every face's type line, lowercased, falling back to the combined one."""
    lines = [
        (face.get("type_line") or "").lower() for face in card_data.get("faces", [])
    ]
    lines = [line for line in lines if line]
    return lines or [(card_data.get("type_line") or "").lower()]


def _pips_in_cost(mana_cost: str) -> dict:
    """Colored pips a single mana cost string asks for, per WUBRG letter.

    A hybrid or Phyrexian symbol counts for *each* color it can be paid with,
    because each one is a color the deck has to be able to produce.
    """
    pips = _empty_counts()
    for symbol in _MANA_SYMBOL_RE.findall(mana_cost or ""):
        # A set, so a symbol never counts twice for the same color.
        for letter in {ch for ch in symbol.upper() if ch in WUBRG}:
            pips[letter] += 1
    return pips


def _face_mana_value(mana_cost: str) -> int:
    """The mana value a single face's own mana cost contributes.

    Per the comprehensive rules: a numeric symbol contributes its number
    (``{3}`` -> 3); ``{X}`` contributes 0; a monocolor hybrid contributes its
    number (``{2/W}`` -> 2); every other symbol — colored, two-color hybrid or
    Phyrexian (``{W}``, ``{W/U}``, ``{W/P}``) — contributes 1.
    """
    total = 0
    for symbol in _MANA_SYMBOL_RE.findall(mana_cost or ""):
        if symbol.isdigit():
            total += int(symbol)
        elif symbol.upper() == "X":
            continue
        elif "/" in symbol:
            numeric_half = next((part for part in symbol.split("/") if part.isdigit()), None)
            total += int(numeric_half) if numeric_half is not None else 1
        else:
            total += 1
    return total


def card_pips(card_data: dict) -> dict:
    """Colored pips a card's mana costs ask for, per WUBRG letter.

    Every face that has a mana cost counts, so both halves of a split card are
    counted and a transform back (which has none) adds nothing. Both halves of
    an adventure or a modal DFC are genuinely castable, so their pips are
    summed here too.
    """
    pips = _empty_counts()
    for face in card_data.get("faces", []):
        face_pips = _pips_in_cost(face.get("mana_cost") or "")
        for letter, count in face_pips.items():
            pips[letter] += count
    return pips


def deck_pips(processed_cards: list) -> dict:
    """The deck's total colored pips, weighted by quantity.

    The commander is included: cast from the command zone or not, its cost is
    the deck's most binding color requirement.
    """
    totals = _empty_counts()
    for item in processed_cards:
        for letter, count in card_pips(item["data"]).items():
            totals[letter] += count * item["quantity"]
    return totals


def produced_colors(card_data: dict) -> list:
    """WUBRG letters a card can be tapped for, in canonical order.

    Empty when the card is not a colored mana source: it produces nothing, it
    produces only colorless, or it makes mana without ever sitting on the
    battlefield. Decks analyzed before ``produced_mana`` was stored carry no
    such field and report no sources until they are re-analyzed.
    """
    produced = card_data.get("produced_mana") or []
    if not produced:
        return []
    # Any face being a permanent is enough: a modal card with a land back
    # (Agadeem's Awakening) is a real source even though its front is a spell.
    if not any(
        source_type in line for line in _type_lines(card_data)
        for source_type in _SOURCE_TYPES
    ):
        return []
    return [color for color in WUBRG if color in produced]


def deck_sources(processed_cards: list) -> dict:
    """Colored sources the deck's *library* offers, per WUBRG letter.

    The commander is excluded: it is never drawn, so it can never be the fixing
    that makes a spell castable.
    """
    totals = _empty_counts()
    for item in processed_cards:
        if item.get("is_commander"):
            continue
        for letter in produced_colors(item["data"]):
            totals[letter] += item["quantity"]
    return totals


# Card types that stay on the battlefield. Everything else that is not a land
# — instants and sorceries — is a spell, which is the split Moxfield's curve
# shows and the only one that needs naming here.
PERMANENT_TYPES = ("creature", "artifact", "enchantment", "planeswalker", "battle")


def mana_curve(processed_cards: list) -> list:
    """Cards per mana value, lands out, permanents and spells kept apart.

    The commander is excluded: it starts in the command zone rather than the
    deck, so it is not part of the curve you draw into. (Moxfield does the
    same, which is how the reference deck's curve sums to its 74 non-lands.)
    """
    buckets = [{"permanents": 0, "spells": 0} for _ in range(CURVE_BUCKETS)]

    for item in processed_cards:
        if item.get("is_commander"):
            continue
        data = item["data"]
        if classify_card(data) == "Land":
            continue
        value = min(int(data.get("cmc", 0) or 0), CURVE_BUCKETS - 1)
        type_line = front_type_line(data)
        key = (
            "permanents"
            if any(t in type_line for t in PERMANENT_TYPES)
            else "spells"
        )
        buckets[value][key] += item["quantity"]

    return buckets


# The opening hand's size: the cards a player starts with before the London
# mulligan considerations even come up.
OPENING_HAND_SIZE = 7


def cards_seen(turn: int) -> int:
    """Cards seen by ``turn`` on the play: the opening seven, plus one a turn."""
    return OPENING_HAND_SIZE + max(0, turn - 1)


def is_land_card(card_data: dict) -> bool:
    """Whether any of a card's faces is a land.

    Deliberately different from :func:`~.cards.classify_card`, which reads the
    front face only and decides what the card is *cast as*. Here the question
    is what the card can be tapped for, so a modal card with a land back
    (Sink into Stupor, Hydroelectric Specimen) counts — which is also how
    Moxfield reaches the land count its mana figures are built on.
    """
    return any("land" in line for line in _type_lines(card_data))


def land_production(processed_cards: list) -> dict:
    """How many lands the deck plays, and what they can be tapped for.

    ``symbol_slots`` counts one slot per color per land: a Command Tower fills
    five, an Island one, a land with no mana ability none. It is the
    denominator behind "N% of symbols on lands"; ``lands`` is the denominator
    behind "N% mana production".
    """
    lands = 0
    slots = 0
    by_color = {color: 0 for color in list(WUBRG) + ["C"]}

    for item in processed_cards:
        data = item["data"]
        if not is_land_card(data):
            continue
        quantity = item["quantity"]
        lands += quantity
        produced = data.get("produced_mana") or []
        for color in by_color:
            if color in produced:
                by_color[color] += quantity
                slots += quantity

    return {"lands": lands, "symbol_slots": slots, "by_color": by_color}
