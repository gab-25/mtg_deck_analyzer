"""Tests for the web storage helpers (image key (de)serialization)."""

import io

from mtg_deck_analyzer.domain.storage import (
    cards_for_pdf,
    cards_for_storage,
    image_urls,
    proxy_images,
)

# Smallest valid 1x1 transparent PNG.
_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6360000002000154a24f5f0000000049454e44ae426082"
)


class _FakeCache:
    def __init__(self, images):
        self.images = images

    def get_image(self, name):
        return self.images.get(name)


def _cards(paths):
    return [{"quantity": 2, "data": {"name": "Forest", "image_paths": list(paths)}}]


def test_cards_for_storage_reduces_to_basenames():
    cards = _cards(["/abs/cache/images/img_a_en.jpg", "img_b_en.jpg"])
    stored = cards_for_storage(cards)
    assert stored[0]["data"]["image_paths"] == ["img_a_en.jpg", "img_b_en.jpg"]
    # Original list is left untouched (deep copy).
    assert cards[0]["data"]["image_paths"][0] == "/abs/cache/images/img_a_en.jpg"


def test_cards_for_pdf_resolves_only_present_images():
    cache = _FakeCache({"img_real.jpg": _PNG})
    stored = _cards(["img_real.jpg", "img_missing.jpg"])
    rebuilt = cards_for_pdf(stored, cache)
    streams = rebuilt[0]["data"]["image_paths"]
    assert len(streams) == 1  # the missing one is dropped
    assert isinstance(streams[0], io.BytesIO)
    assert streams[0].getvalue() == _PNG


def test_proxy_images_repeats_each_card_by_quantity():
    cache = _FakeCache({"img_a.jpg": _PNG})
    stored = [
        {"quantity": 3, "data": {"name": "Forest", "image_paths": ["img_a.jpg"]}},
        {"quantity": 1, "data": {"name": "Island", "image_paths": ["img_a.jpg"]}},
    ]
    images = proxy_images(stored, cache)
    # One image per physical card copy: total images == total card count.
    assert len(images) == 4
    # Each copy is its own stream (ReportLab consumes them independently).
    assert all(isinstance(s, io.BytesIO) for s in images)
    assert len({id(s) for s in images}) == 4
    assert all(s.getvalue() == _PNG for s in images)


def test_proxy_images_missing_image_yields_placeholder_slots():
    cache = _FakeCache({})
    stored = [{"quantity": 2, "data": {"name": "Forest", "image_paths": []}}]
    images = proxy_images(stored, cache)
    # Still one slot per copy so the total matches the deck; slots are None.
    assert images == [None, None]


def test_proxy_images_skips_basic_lands():
    cache = _FakeCache({"forest.jpg": _PNG, "bolt.jpg": _PNG})
    stored = [
        {
            "quantity": 10,
            "data": {
                "name": "Forest",
                "type_line": "Basic Land — Forest",
                "image_paths": ["forest.jpg"],
            },
        },
        {
            "quantity": 4,
            "data": {
                "name": "Lightning Bolt",
                "type_line": "Instant",
                "image_paths": ["bolt.jpg"],
            },
        },
    ]
    images = proxy_images(stored, cache)
    # Basic lands are excluded; only the 4 non-basic copies remain.
    assert len(images) == 4


def test_image_urls_uses_media_prefix():
    data = {"image_paths": ["img_a_en.jpg", "img_b_en.jpg"]}
    assert image_urls(data) == ["/media/img_a_en.jpg", "/media/img_b_en.jpg"]
    assert image_urls(data, media_prefix="/x") == ["/x/img_a_en.jpg", "/x/img_b_en.jpg"]
