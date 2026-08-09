"""Parsing of plain-text Commander decklists."""

import os
import re
import sys

# Section headers that introduce the commander(s).
_COMMANDER_HEADERS = {"commander", "commanders"}

# Every other header exports carry. The cards below them are part of the deck
# all the same — Commander has no sideboard, so anything pasted in counts
# towards the 100 cards and is flagged by the legality check if it overflows.
_MAIN_HEADERS = {
    "deck",
    "main",
    "mainboard",
    "sideboard",
    "maybeboard",
    "companion",
    "considering",
}

_SECTION_HEADERS = _COMMANDER_HEADERS | _MAIN_HEADERS

# "4 Lightning Bolt" and the "4x Lightning Bolt" spelling used by several
# deckbuilding sites.
_CARD_PATTERN = re.compile(r"^(\d+)\s*[xX]?\s+(.+?)$")

# Inline commander marker appended by Moxfield/Archidekt exports, e.g.
# "1 Atraxa, Praetors' Voice *CMDR*".
_COMMANDER_MARKER = re.compile(r"\s*\*\s*(?:CMDR|COMMANDER)\s*\*\s*$", re.IGNORECASE)


def parse_decklist_text(text: str) -> list:
    """Parses raw decklist text into ``{quantity, name, is_commander}`` dicts.

    Commanders are the cards listed under a ``Commander`` section header or
    tagged with a trailing ``*CMDR*`` marker; every other card belongs to the
    deck.
    """
    cards = []
    in_commander_section = False

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # Ignore comments.
        if line.startswith("//") or line.startswith("#"):
            continue

        # A bare section header switches the section the following cards land in.
        header = line.lower().rstrip(":")
        if header in _SECTION_HEADERS:
            in_commander_section = header in _COMMANDER_HEADERS
            continue

        line, marked = _strip_commander_marker(line)

        match = _CARD_PATTERN.match(line)
        if match:
            qty = int(match.group(1))
            name = match.group(2).strip()
        else:
            # Fallback for lines without a quantity prefix.
            qty = 1
            name = line

        if not name:
            continue

        cards.append(
            {
                "quantity": qty,
                "name": name,
                "is_commander": marked or in_commander_section,
            }
        )

    return cards


def _strip_commander_marker(line: str) -> tuple:
    """Splits a trailing ``*CMDR*`` marker off a card line.

    Returns ``(line_without_marker, was_marked)``.
    """
    stripped = _COMMANDER_MARKER.sub("", line)
    return stripped.strip(), stripped != line


def parse_decklist(file_path: str) -> list:
    """Parses a text decklist file and returns a list of card dicts."""
    if not os.path.exists(file_path):
        print(f"Error: Decklist file not found at {file_path}", file=sys.stderr)
        return []

    with open(file_path, "r", encoding="utf-8") as f:
        return parse_decklist_text(f.read())
