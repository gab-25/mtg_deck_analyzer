"""Commander (EDH) format rules: color identity and deck legality.

Pure functions, no I/O. A deck is checked in two passes, because the rules need
different data:

* :func:`check_decklist` runs on the parsed decklist entries (names only), so
  the web form can reject an illegal deck instantly.
* :func:`check_deck` runs on the *processed cards* — the ``{"quantity",
  "is_commander", "data"}`` dicts built from Scryfall data — and covers the
  rules that need the real card (commander eligibility, color identity, and
  the ban list of the deck's format).
"""

import re

from .cards import front_type_line, is_basic_land, rules_text
from .constants import (
    ANY_NUMBER_CARD_NAMES,
    BASIC_LAND_NAMES,
    CAN_BE_COMMANDER_TEXT,
    COMMANDER_DECK_SIZE,
    DEFAULT_FORMAT,
    FORMATS,
    MAX_COMMANDERS,
    UNLIMITED_COPIES_TEXT,
)
from .text_utils import front_face_name

# Canonical color order (Magic's "WUBRG" wheel).
WUBRG = "WUBRG"

_MANA_SYMBOL_RE = re.compile(r"\{([^}]+)\}")


def card_color_identity(card_data: dict) -> list:
    """Returns a card's color identity as WUBRG letters, in canonical order.

    Prefers Scryfall's ``color_identity``; decks stored before it was persisted
    fall back to the colors of the mana symbols printed on their faces (a close
    approximation that misses only off-color rules text).
    """
    identity = card_data.get("color_identity")
    if identity is None:
        found = set()
        for face in card_data.get("faces", []):
            for symbol in _MANA_SYMBOL_RE.findall(face.get("mana_cost") or ""):
                found.update(ch for ch in symbol if ch in WUBRG)
        identity = found
    return [c for c in WUBRG if c in identity]


def commanders(processed_cards: list) -> list:
    """Returns the cards flagged as commanders, in decklist order."""
    return [item for item in processed_cards if item.get("is_commander")]


def commander_names(processed_cards: list) -> list:
    """Returns the names of the deck's commander(s)."""
    return [item["data"].get("name", "") for item in commanders(processed_cards)]


def deck_color_identity(processed_cards: list) -> list:
    """Returns the deck's color identity: the union of its commanders' colors.

    With no commander declared there is nothing to derive the identity from, so
    the whole deck's colors are used instead — which is what the deck would play
    anyway.
    """
    source = commanders(processed_cards) or processed_cards
    found = set()
    for item in source:
        found.update(card_color_identity(item["data"]))
    return [c for c in WUBRG if c in found]


def _can_be_commander(card_data: dict) -> bool:
    """Reports whether a card may be designated as a commander."""
    # The front face is the one that goes in the command zone: a card that
    # merely transforms into a legendary creature (Bloodline Keeper) is not a
    # legal commander.
    type_line = front_type_line(card_data)
    if "legendary" in type_line and "creature" in type_line:
        return True
    return CAN_BE_COMMANDER_TEXT in rules_text(card_data)


def _allows_duplicates(card_data: dict) -> bool:
    """Reports whether a card is exempt from the singleton rule."""
    return is_basic_land(card_data) or UNLIMITED_COPIES_TEXT in rules_text(card_data)


def _format_identity(identity: list) -> str:
    """Renders a color identity for a message: ``{W}{U}`` or ``colorless``."""
    return "".join(f"{{{c}}}" for c in identity) if identity else "colorless"


def _size_issue(total: int) -> list:
    """The 100-card rule, shared by both passes."""
    if total == COMMANDER_DECK_SIZE:
        return []
    return [
        f"The deck has {total} cards: Commander requires exactly "
        f"{COMMANDER_DECK_SIZE}, commander included."
    ]


def _commander_count_issues(count: int) -> list:
    """The "exactly one commander" rule, shared by both passes."""
    if count == 0:
        return [
            "No commander declared: list it under a “Commander” header or tag "
            "its line with *CMDR*."
        ]
    if count > MAX_COMMANDERS:
        return [
            f"{count} commanders declared: a deck has exactly "
            f"{MAX_COMMANDERS} commander."
        ]
    return []


def _singleton_issue(name: str, qty: int) -> list:
    """The singleton rule's message for one entry."""
    return [
        f"{qty}× “{name}”: Commander is singleton, only one copy of each card "
        "is allowed (basic lands aside)."
    ]


def _tally(entries) -> dict:
    """Totals ``(key, card, quantity)`` triples per card, in first-seen order.

    Returns ``{key: (card, total_quantity)}``. One card can take up several
    decklist lines — twice under the same name, or once per spelling of a
    double-faced card — and the singleton rule counts copies, not lines.
    """
    totals = {}
    for key, card, qty in entries:
        known, total = totals.get(key, (card, 0))
        totals[key] = (known, total + qty)
    return totals


def check_decklist(entries: list) -> list:
    """Checks the parsed decklist — names and quantities only.

    Returns every problem that can be spotted without fetching the cards, so the
    creation form can reject an illegal deck on the spot instead of spending
    minutes on Scryfall first. An empty list means nothing is wrong *yet*:
    :func:`check_deck` still has the last word.
    """
    issues = _size_issue(sum(entry["quantity"] for entry in entries))
    issues += _commander_count_issues(
        sum(1 for entry in entries if entry.get("is_commander"))
    )

    totals = _tally(
        (front_face_name(entry["name"]).lower(), entry["name"], entry["quantity"])
        for entry in entries
    )
    for key, (name, qty) in totals.items():
        if qty > 1 and key not in BASIC_LAND_NAMES | ANY_NUMBER_CARD_NAMES:
            issues += _singleton_issue(name, qty)

    return issues


def check_deck(processed_cards: list, fmt: str = DEFAULT_FORMAT) -> list:
    """Checks the fetched deck against the deck-construction rules of ``fmt``.

    Re-runs the structural checks on the real cards (quantities can only be
    trusted once every name has resolved) and adds the rules that need Scryfall
    data: commander eligibility, color identity and the ban list. Only the ban
    list varies with the format — construction is identical across them.
    Returns every problem at once, so the caller can report them all together.
    """
    issues = _size_issue(sum(item["quantity"] for item in processed_cards))

    cmdrs = commanders(processed_cards)
    issues += _commander_count_issues(len(cmdrs))

    for item in cmdrs:
        if not _can_be_commander(item["data"]):
            name = item["data"].get("name", "Unknown card")
            issues.append(
                f"“{name}” cannot be a commander: it is neither a legendary "
                "creature nor a card that says it can be your commander."
            )

    # The Scryfall id is the same for both spellings of a double-faced card.
    totals = _tally(
        (
            item["data"].get("id") or item["data"].get("name", ""),
            item["data"],
            item["quantity"],
        )
        for item in processed_cards
    )
    for card, qty in totals.values():
        if qty > 1 and not _allows_duplicates(card):
            issues += _singleton_issue(card.get("name", "Unknown card"), qty)

    issues.extend(_color_identity_issues(processed_cards, cmdrs))
    issues.extend(_legality_issues(processed_cards, fmt))

    return issues


def _color_identity_issues(processed_cards: list, cmdrs: list) -> list:
    """Lists the cards whose color identity the commander does not cover."""
    if not cmdrs:
        return []  # Without a commander there is no identity to check against.

    allowed = set()
    for item in cmdrs:
        allowed.update(card_color_identity(item["data"]))

    issues = []
    for item in processed_cards:
        identity = set(card_color_identity(item["data"]))
        outside = identity - allowed
        if outside:
            name = item["data"].get("name", "Unknown card")
            issues.append(
                f"“{name}” ({_format_identity(sorted(outside, key=WUBRG.index))}) "
                f"falls outside the commander's color identity "
                f"({_format_identity([c for c in WUBRG if c in allowed])})."
            )
    return issues


def _legality_issues(processed_cards: list, fmt: str = DEFAULT_FORMAT) -> list:
    """Lists the cards the given format does not allow.

    Reads the format's own key inside Scryfall's ``legalities``, which separates
    a card banned from an otherwise legal pool (Black Lotus) from one that was
    never printed in a legal product (un-sets, Alchemy rebalances, playtest
    cards). Anything else — including a missing field, as on decks analyzed
    before it was persisted — counts as legal: an absent field must never fail
    a deck.

    The two lists genuinely differ: Sol Ring is legal in Commander and banned
    in Duel Commander.
    """
    rules = FORMATS[fmt]
    issues = []
    for item in processed_cards:
        card = item["data"]
        legality = (card.get("legalities") or {}).get(rules.legality_key)
        if legality not in ("banned", "not_legal"):
            continue
        name = card.get("name", "Unknown card")
        if legality == "banned":
            issues.append(f"“{name}” is banned in {rules.label}.")
        else:
            issues.append(f"“{name}” is not legal in {rules.label}.")
    return issues
