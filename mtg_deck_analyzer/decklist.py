"""Parsing of plain-text decklist files."""

import os
import re
import sys

# Standard categories/headers to ignore when a line has no quantity.
_CATEGORY_HEADERS = {"deck", "sideboard", "commander", "mainboard", "companion"}

_CARD_PATTERN = re.compile(r"^\s*(\d+)\s+(.+?)\s*$")


def parse_decklist_text(text: str) -> list:
    """Parses raw decklist text and returns a list of card dicts."""
    cards = []

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # Ignore comments or headers.
        if line.startswith("//") or line.startswith("#"):
            continue

        match = _CARD_PATTERN.match(line)
        if match:
            qty = int(match.group(1))
            name = match.group(2)
            cards.append({"quantity": qty, "name": name})
        else:
            # Fallback for lines without a quantity prefix,
            # ignoring standard category headers.
            if line.lower() not in _CATEGORY_HEADERS:
                cards.append({"quantity": 1, "name": line})

    return cards


def parse_decklist(file_path: str) -> list:
    """Parses a text decklist file and returns a list of card dicts."""
    if not os.path.exists(file_path):
        print(f"Error: Decklist file not found at {file_path}", file=sys.stderr)
        return []

    with open(file_path, "r", encoding="utf-8") as f:
        return parse_decklist_text(f.read())
