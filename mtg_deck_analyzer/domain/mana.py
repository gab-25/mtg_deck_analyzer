"""What the deck asks for in colored mana, and what it offers.

Pure functions over the processed cards. Three counts read straight off the
cards — the pips a deck's costs demand, the sources that can pay them and the
mana curve — plus (see :mod:`.statistics`) the verdict that puts the first two
next to each other.
"""

import re

from .cards import classify_card
from .commander import WUBRG
from .probability import min_successes_for

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
    summed here too — see :func:`_hardest_cast` for why they are not paired
    with the card's overall mana value.
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


def mana_curve(processed_cards: list) -> list:
    """Card count per mana value, lands excluded, everything 7+ merged.

    An average collapses the shape it is worth seeing: ten one-drops and ten
    seven-drops average out to the same number as twenty four-drops.
    """
    buckets = [0] * CURVE_BUCKETS
    for item in processed_cards:
        data = item["data"]
        if classify_card(data) == "Land":
            continue
        value = min(int(data.get("cmc", 0) or 0), CURVE_BUCKETS - 1)
        buckets[value] += item["quantity"]
    return buckets


# The opening hand, and the confidence the color-fixing verdict is held to.
OPENING_HAND_SIZE = 7
FIXING_CONFIDENCE = 0.90


def cards_seen(turn: int) -> int:
    """Cards seen by ``turn`` on the play: the opening seven, plus one a turn."""
    return OPENING_HAND_SIZE + max(0, turn - 1)


def sources_required(pips: int, turn: int, library_size: int) -> int | None:
    """Sources needed to have ``pips`` of them in hand by ``turn``.

    This is Karsten's question — "how many sources does this card need to be
    castable on curve?" — answered against *this* deck's library instead of a
    table printed for 60-card decks: the fewest sources that put ``pips`` of
    them among the cards seen by then, :data:`FIXING_CONFIDENCE` of the time.

    A strict threshold, and stricter than the published tables, which also
    model the London mulligan and fetchlands. ``None`` when no count reaches
    it, which only happens on a library too small to hold the requirement.
    """
    return min_successes_for(
        library_size, cards_seen(turn), pips, FIXING_CONFIDENCE
    )


def _hardest_cast(processed_cards: list, color: str, library_size: int) -> dict:
    """The face that asks the most of ``color``, and what it asks for.

    "Most" is measured in sources required, not in pips: a triple-pip seven-drop
    has four extra turns to find its mana, and is an easier cast than a
    double-pip two-drop.

    Judged **per face**, not per card: for a split card Scryfall's ``cmc`` is
    the sum of both halves, so pairing a card's summed pips with its ``cmc``
    is fine. For an adventure or a modal DFC, ``cmc`` is the *front face only*
    — pairing the summed pips with it would pair one face's mana value with
    the other face's colors. Each face is judged on its own cost instead.
    """
    hardest = {"demand_card": "", "demand_pips": 0, "demand_turn": 0, "required": 0}
    for item in processed_cards:
        data = item["data"]
        for face in data.get("faces", []):
            mana_cost = face.get("mana_cost") or ""
            pips = _pips_in_cost(mana_cost)[color]
            if not pips:
                continue
            # A face cannot be cast before its own mana value allows.
            turn = max(1, _face_mana_value(mana_cost))
            required = sources_required(pips, turn, library_size)
            # An unreachable requirement outranks every reachable one.
            if required is None or hardest["required"] is None:
                better = required is None
            else:
                better = required > hardest["required"]
            if better:
                hardest = {
                    "demand_card": data.get("name", ""),
                    "demand_pips": pips,
                    "demand_turn": turn,
                    "required": required,
                }
    return hardest


def color_fixing(processed_cards: list, library_size: int) -> list:
    """Per color: pips asked for, sources offered and the gap between them.

    One entry per color the deck touches at all, in WUBRG order. ``shortfall``
    is how many sources are missing (0 when the deck is fine, ``None`` when the
    requirement cannot be met at all).
    """
    pips = deck_pips(processed_cards)
    sources = deck_sources(processed_cards)

    entries = []
    for color in WUBRG:
        if not pips[color] and not sources[color]:
            continue
        hardest = _hardest_cast(processed_cards, color, library_size)
        required = hardest["required"]
        entries.append(
            {
                "color": color,
                "pips": pips[color],
                "sources": sources[color],
                "shortfall": (
                    None if required is None else max(0, required - sources[color])
                ),
                **hardest,
            }
        )
    return entries
