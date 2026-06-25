"""Helpers to move processed cards between the cache, the DB and the views.

Scryfall card images are cached as bytes (by basename) in the cache backend.
The persisted deck keeps only those basenames; they are turned into ``/media``
URLs for the web pages and read back as in-memory images for PDF generation.
"""

import copy
import io
import os


def cards_for_storage(processed_cards: list) -> list:
    """Returns a copy of ``processed_cards`` with image keys reduced to basenames.

    ``image_paths`` already holds cache keys (basenames); ``basename`` keeps this
    idempotent and tolerant of any absolute paths from a filesystem cache.
    """
    stored = copy.deepcopy(processed_cards)
    for item in stored:
        data = item.get("data", {})
        data["image_paths"] = [
            os.path.basename(p) for p in data.get("image_paths", [])
        ]
    return stored


def cards_for_pdf(stored_cards: list, cache) -> list:
    """Resolves stored image keys to in-memory streams for PDF generation.

    Reads each image's bytes from ``cache`` and wraps them in ``BytesIO`` (which
    ReportLab's ``Image`` accepts directly); missing images are dropped (the PDF
    renderer falls back to a placeholder).
    """
    cards = copy.deepcopy(stored_cards)
    for item in cards:
        data = item.get("data", {})
        streams = []
        for name in data.get("image_paths", []):
            raw = cache.get_image(name)
            if raw:
                streams.append(io.BytesIO(raw))
        data["image_paths"] = streams
    return cards


def image_urls(card_data: dict, media_prefix: str = "/media") -> list:
    """Maps a stored card's image basenames to servable URLs."""
    return [f"{media_prefix}/{name}" for name in card_data.get("image_paths", [])]
