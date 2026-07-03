"""Helpers to move processed cards between the cache, the DB and the views.

Scryfall card images are cached as bytes (by basename) in the cache backend.
The persisted deck keeps only those basenames; they are turned into ``/media``
URLs for the web pages and read back as in-memory images for PDF generation.
"""

import copy
import io
import os

from .cards import is_basic_land


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


def proxy_images(stored_cards: list, cache) -> list:
    """Flat list of one front-face image stream per physical card copy.

    Each card contributes ``quantity`` copies of its front image so the number of
    proxy images equals the deck's total card count. A fresh ``BytesIO`` is made
    for every copy (ReportLab consumes the stream while building, so copies must
    not share one). Cards with no cached image yield ``quantity`` ``None`` slots,
    which the renderer turns into placeholders.

    Basic lands are skipped: they're trivially available in paper, so there's no
    point printing proxies for them.
    """
    images = []
    for item in stored_cards:
        data = item.get("data", {})
        if is_basic_land(data):
            continue
        qty = item.get("quantity", 1)
        names = data.get("image_paths", [])
        raw = cache.get_image(names[0]) if names else None
        for _ in range(qty):
            images.append(io.BytesIO(raw) if raw else None)
    return images


def image_urls(card_data: dict, media_prefix: str = "/media") -> list:
    """Maps a stored card's image basenames to servable URLs."""
    return [f"{media_prefix}/{name}" for name in card_data.get("image_paths", [])]
