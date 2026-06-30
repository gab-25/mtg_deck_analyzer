"""Tests for the Scryfall cache backends (filesystem and database)."""

import pytest

from mtg_deck_analyzer.db_cache import DbCardCache
from mtg_deck_analyzer.scryfall import FileCardCache, fetch_card_data


def _exercise_cache(cache):
    # Cards.
    assert cache.get_card("card_en_forest") is None
    cache.set_card("card_en_forest", {"name": "Forest", "lang": "en"})
    assert cache.get_card("card_en_forest") == {"name": "Forest", "lang": "en"}
    # Overwrite.
    cache.set_card("card_en_forest", {"name": "Forest", "lang": "en", "cmc": 0})
    assert cache.get_card("card_en_forest")["cmc"] == 0

    # Images.
    assert cache.has_image("img_x.jpg") is False
    assert cache.get_image("img_x.jpg") is None
    cache.set_image("img_x.jpg", b"\x01\x02\x03")
    assert cache.has_image("img_x.jpg") is True
    assert cache.get_image("img_x.jpg") == b"\x01\x02\x03"


def test_file_card_cache_roundtrip(tmp_path):
    _exercise_cache(FileCardCache(str(tmp_path)))


@pytest.mark.django_db
def test_db_card_cache_roundtrip():
    _exercise_cache(DbCardCache())


@pytest.mark.django_db
def test_fetch_card_data_uses_cache_without_network():
    """A cached English card is processed straight from the cache (no HTTP)."""
    cache = DbCardCache()
    cache.set_card(
        "card_en_forest",
        {
            "id": "abc",
            "lang": "en",
            "name": "Forest",
            "type_line": "Basic Land — Forest",
            "oracle_text": "({T}: Add {G}.)",
            "cmc": 0.0,
            "prices": {"eur": "0.05"},
        },
    )

    card = fetch_card_data("Forest", "en", cache)
    assert card["name"] == "Forest"
    assert card["price_eur"] == 0.05
    assert card["image_paths"] == []  # no image_uris in the cached payload
    assert card["faces"][0]["rules_text"] == "({T}: Add {G}.)"
    assert card["text_source"] == "official"  # English is always official


@pytest.mark.django_db
def test_fetch_card_data_marks_english_fallback(monkeypatch):
    """A non-English request with only untranslated text and no key -> 'english'."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    cache = DbCardCache()
    cache.set_card(
        "card_it_forest",
        {
            "id": "abc",
            "lang": "en",
            "name": "Forest",
            "type_line": "Basic Land — Forest",
            "oracle_text": "({T}: Add {G}.)",  # no printed_text -> untranslated
            "cmc": 0.0,
        },
    )
    card = fetch_card_data("Forest", "it", cache)
    assert card["text_source"] == "english"


@pytest.mark.django_db
def test_fetch_card_data_returns_none_for_cached_not_found():
    cache = DbCardCache()
    cache.set_card("card_en_nope", {"error": "not_found"})
    assert fetch_card_data("Nope", "en", cache) is None
