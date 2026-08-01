"""Tests for shared domain constants."""

from mtg_deck_analyzer.domain.constants import (
    BASIC_LAND_NAMES,
    CATEGORY_ORDER,
    COMMANDER_DECK_SIZE,
    MAX_COMMANDERS,
)


def test_commander_deck_construction_constants():
    assert COMMANDER_DECK_SIZE == 100
    # A single commander: partners and backgrounds are deliberately not allowed.
    assert MAX_COMMANDERS == 1


def test_basic_land_names_cover_the_five_basics_and_their_snow_variants():
    for base in ("plains", "island", "swamp", "mountain", "forest"):
        assert base in BASIC_LAND_NAMES
        assert f"snow-covered {base}" in BASIC_LAND_NAMES
    assert "wastes" in BASIC_LAND_NAMES


def test_category_order_covers_main_types():
    for category in ("Creature", "Land", "Instant", "Sorcery", "Other"):
        assert category in CATEGORY_ORDER
