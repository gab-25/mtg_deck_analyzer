"""What changed between two submitted decklists."""

from collections import defaultdict

from .decklist import parse_decklist_text


def _quantities(text: str) -> dict:
    """Total copies per card name in a decklist, commander section included.

    Sections don't matter here: a card promoted to commander is the same card
    in the same count, and reporting that as a swap would be noise.
    """
    totals = defaultdict(int)
    for entry in parse_decklist_text(text):
        totals[entry["name"]] += entry["quantity"]
    return totals


def decklist_changes(previous: str, current: str) -> list:
    """Card-level differences between two decklists.

    Returns ``{"sign": "+" | "-", "quantity": int, "name": str}`` entries —
    additions first, removals after, each group alphabetical — so the trail
    reads the way deck building is actually thought about: ``+1 Rhystic Study``
    next to ``-1 Arcane Signet``. A count that moved reports only the
    difference, and an unchanged card reports nothing at all.
    """
    before = _quantities(previous)
    after = _quantities(current)

    added, removed = [], []
    for name in sorted(before.keys() | after.keys()):
        delta = after.get(name, 0) - before.get(name, 0)
        if delta > 0:
            added.append({"sign": "+", "quantity": delta, "name": name})
        elif delta < 0:
            removed.append({"sign": "-", "quantity": -delta, "name": name})
    return added + removed
