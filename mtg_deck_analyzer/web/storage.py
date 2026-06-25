"""Helpers to move processed cards between the cache, the DB and the views.

Scryfall images are downloaded into the local cache as absolute file paths. For
persistence we keep only the image *basename*; the actual bytes stay in the
cache directory, which is served as static files by the web app and read back
when regenerating the PDF.
"""

import copy
import os


def cards_for_storage(processed_cards: list) -> list:
    """Returns a copy of ``processed_cards`` with image paths reduced to basenames."""
    stored = copy.deepcopy(processed_cards)
    for item in stored:
        data = item.get("data", {})
        data["image_paths"] = [
            os.path.basename(p) for p in data.get("image_paths", [])
        ]
    return stored


def cards_for_pdf(stored_cards: list, images_dir: str) -> list:
    """Rebuilds absolute image paths from basenames for PDF generation.

    Missing files are dropped; the PDF renderer falls back to a placeholder.
    """
    cards = copy.deepcopy(stored_cards)
    for item in cards:
        data = item.get("data", {})
        abs_paths = []
        for name in data.get("image_paths", []):
            path = os.path.join(images_dir, name)
            if os.path.exists(path):
                abs_paths.append(path)
        data["image_paths"] = abs_paths
    return cards


def image_urls(card_data: dict, media_prefix: str = "/media") -> list:
    """Maps a stored card's image basenames to servable URLs."""
    return [f"{media_prefix}/{name}" for name in card_data.get("image_paths", [])]
