"""Tests for the Scryfall cache backends (filesystem and database)."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from mtg_deck_analyzer.scryfall import FileCardCache, fetch_card_data
from mtg_deck_analyzer.web.db import Base
from mtg_deck_analyzer.web.db_cache import DbCardCache


@pytest.fixture
def db_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


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


def test_db_card_cache_roundtrip(db_session):
    _exercise_cache(DbCardCache(db_session))


def test_fetch_card_data_uses_cache_without_network(db_session):
    """A cached English card is processed straight from the cache (no HTTP)."""
    cache = DbCardCache(db_session)
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


def test_fetch_card_data_returns_none_for_cached_not_found(db_session):
    cache = DbCardCache(db_session)
    cache.set_card("card_en_nope", {"error": "not_found"})
    assert fetch_card_data("Nope", "en", cache) is None
