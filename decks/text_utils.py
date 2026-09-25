"""Card-name helpers."""

import re


def front_face_name(name: str) -> str:
    """Returns the front face of a card name written in full (``"A // B"`` -> ``"A"``).

    A double-faced card can be listed either way and Scryfall resolves both to
    the same card, so the front face — whose name is unique on its own — stands
    for the whole card.
    """
    return name.split("//")[0].strip()


def card_slug(name: str) -> str:
    """Creates a filesystem-safe slug from a card name."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
