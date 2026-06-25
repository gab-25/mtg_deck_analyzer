"""Tests for the web storage helpers (image path (de)serialization)."""

import os

from mtg_deck_analyzer.web.storage import (
    cards_for_pdf,
    cards_for_storage,
    image_urls,
)


def _cards(paths):
    return [{"quantity": 2, "data": {"name": "Forest", "image_paths": list(paths)}}]


def test_cards_for_storage_reduces_to_basenames():
    cards = _cards(["/abs/cache/images/img_a_en.jpg", "/abs/cache/images/img_b_en.jpg"])
    stored = cards_for_storage(cards)
    assert stored[0]["data"]["image_paths"] == ["img_a_en.jpg", "img_b_en.jpg"]
    # Original list is left untouched (deep copy).
    assert cards[0]["data"]["image_paths"][0] == "/abs/cache/images/img_a_en.jpg"


def test_cards_for_pdf_rebuilds_only_existing_files(tmp_path):
    real = tmp_path / "img_real.jpg"
    real.write_bytes(b"x")
    stored = _cards(["img_real.jpg", "img_missing.jpg"])
    rebuilt = cards_for_pdf(stored, str(tmp_path))
    assert rebuilt[0]["data"]["image_paths"] == [os.path.join(str(tmp_path), "img_real.jpg")]


def test_image_urls_uses_media_prefix():
    data = {"image_paths": ["img_a_en.jpg", "img_b_en.jpg"]}
    assert image_urls(data) == ["/media/img_a_en.jpg", "/media/img_b_en.jpg"]
    assert image_urls(data, media_prefix="/x") == ["/x/img_a_en.jpg", "/x/img_b_en.jpg"]
