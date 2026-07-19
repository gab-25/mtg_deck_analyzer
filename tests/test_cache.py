"""Tests for the Scryfall cache backends (filesystem and database)."""

import pytest

from mtg_deck_analyzer.caching.db_cache import DbCardCache
from mtg_deck_analyzer.caching.file_cache import FileCardCache
from mtg_deck_analyzer.integrations.scryfall import fetch_card_data


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

    card = fetch_card_data("Forest", cache)
    assert card["name"] == "Forest"
    assert card["price_eur"] == 0.05
    assert card["image_paths"] == []  # no image_uris in the cached payload
    assert card["faces"][0]["rules_text"] == "({T}: Add {G}.)"


@pytest.mark.django_db
def test_fetch_card_data_returns_none_for_cached_not_found():
    cache = DbCardCache()
    cache.set_card("card_en_nope", {"error": "not_found"})
    assert fetch_card_data("Nope", cache) is None


@pytest.mark.django_db
def test_purge_non_english_cache_keeps_only_english():
    """The data migration drops localized cache rows and keeps the English ones."""
    import importlib

    from django.apps import apps

    from mtg_deck_analyzer.models import ScryfallCard, ScryfallImage

    migration = importlib.import_module(
        "mtg_deck_analyzer.migrations.0005_purge_non_english_cache"
    )

    cache = DbCardCache()
    # Card JSON: one English, two localized.
    cache.set_card("card_en_forest", {"name": "Forest"})
    cache.set_card("card_it_forest", {"name": "Foresta"})
    cache.set_card("card_de_forest", {"name": "Wald"})
    # Images: English single + face, localized single + face.
    cache.set_image("img_abc_en.jpg", b"\x01")
    cache.set_image("img_abc_en_face0.jpg", b"\x02")
    cache.set_image("img_abc_it.jpg", b"\x03")
    cache.set_image("img_abc_it_face0.jpg", b"\x04")

    migration.purge_non_english_cache(apps, None)

    assert set(ScryfallCard.objects.values_list("key", flat=True)) == {"card_en_forest"}
    assert set(ScryfallImage.objects.values_list("name", flat=True)) == {
        "img_abc_en.jpg",
        "img_abc_en_face0.jpg",
    }
