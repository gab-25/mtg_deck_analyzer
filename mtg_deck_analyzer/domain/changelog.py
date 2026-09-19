"""What changed between two submitted decklists."""

from collections import defaultdict

from .decklist import parse_decklist_text
from .text_utils import front_face_name


def _quantities(text: str) -> dict:
    """Total copies per card (by normalized name) with display name preservation.

    Keys by front_face_name(name).lower() to treat equivalent cards (different
    casing, double-faced variants) as the same. Returns a dict where each key
    maps to {"quantity": int, "display_name": str}.

    Sections don't matter here: a card promoted to commander is the same card
    in the same count, and reporting that as a swap would be noise.
    """
    totals = defaultdict(lambda: {"quantity": 0, "display_name": None})
    for entry in parse_decklist_text(text):
        normalized_key = front_face_name(entry["name"]).lower()
        totals[normalized_key]["quantity"] += entry["quantity"]
        # Keep the display name from this entry (will use the last one seen)
        totals[normalized_key]["display_name"] = entry["name"]
    return totals


def decklist_changes(previous: str, current: str) -> list:
    """Card-level differences between two decklists.

    Returns ``{"sign": "+" | "-", "quantity": int, "name": str}`` entries —
    additions first, removals after, each group alphabetical — so the trail
    reads the way deck building is actually thought about: ``+1 Rhystic Study``
    next to ``-1 Arcane Signet``. A count that moved reports only the
    difference, and an unchanged card reports nothing at all.

    Cards are compared by normalized name (front face, lowercased), but the
    output uses the display name from the current (newer) list when available,
    falling back to the previous list's spelling for removals.
    """
    before = _quantities(previous)
    after = _quantities(current)

    added, removed = [], []
    for key in sorted(before.keys() | after.keys()):
        before_qty = before[key]["quantity"] if key in before else 0
        after_qty = after[key]["quantity"] if key in after else 0
        delta = after_qty - before_qty

        # Determine which spelling to use: prefer current list, fall back to previous
        display_name = (
            after[key]["display_name"]
            if key in after
            else before[key]["display_name"]
        )

        if delta > 0:
            added.append({"sign": "+", "quantity": delta, "name": display_name})
        elif delta < 0:
            removed.append({"sign": "-", "quantity": -delta, "name": display_name})

    return added + removed
