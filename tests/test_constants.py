"""Tests for shared domain constants."""

from mtg_deck_analyzer.domain.constants import CATEGORY_ORDER, DECK_TYPES


def test_deck_types_are_defined():
    assert "Custom" in DECK_TYPES
    assert "Commander / EDH" in DECK_TYPES


def test_category_order_covers_main_types():
    for category in ("Creature", "Land", "Instant", "Sorcery", "Other"):
        assert category in CATEGORY_ORDER
