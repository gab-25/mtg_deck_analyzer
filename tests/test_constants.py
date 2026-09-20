"""Tests for shared domain constants."""

import dataclasses

import pytest

from mtg_deck_analyzer.domain.constants import (
    BASIC_LAND_NAMES,
    BRACKET_LABELS,
    CATEGORY_ORDER,
    COMMANDER_DECK_SIZE,
    DEFAULT_FORMAT,
    EXTRA_TURN_TEXT,
    FORMATS,
    GAME_CHANGER_NAMES,
    MASS_LAND_DENIAL_NAMES,
    MAX_COMMANDERS,
    format_choices,
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


class TestFormats:
    def test_the_default_format_is_commander(self):
        assert DEFAULT_FORMAT == "commander"
        assert DEFAULT_FORMAT in FORMATS

    def test_commander_reads_the_commander_legality_key(self):
        assert FORMATS["commander"].legality_key == "commander"
        assert FORMATS["commander"].life == 40

    def test_duel_reads_the_duel_legality_key(self):
        assert FORMATS["duel"].legality_key == "duel"
        assert FORMATS["duel"].life == 20

    def test_every_format_is_fully_described(self):
        for key, fmt in FORMATS.items():
            assert fmt.label, key
            assert fmt.legality_key, key
            assert fmt.life > 0, key
            assert fmt.context, key

    def test_format_choices_feeds_django_textchoices(self):
        assert format_choices() == [
            ("commander", "Commander"),
            ("duel", "Duel Commander"),
        ]

    def test_formats_are_immutable(self):
        with pytest.raises(dataclasses.FrozenInstanceError):
            FORMATS["commander"].life = 20


def test_game_changer_names_hold_the_official_53_front_faces():
    assert len(GAME_CHANGER_NAMES) == 53
    assert "rhystic study" in GAME_CHANGER_NAMES
    assert "smothering tithe" in GAME_CHANGER_NAMES
    # Stored by front face: the list is matched through ``front_face_name``.
    assert "tergrid, god of fright" in GAME_CHANGER_NAMES
    assert all(name == name.lower() for name in GAME_CHANGER_NAMES)


def test_mass_land_denial_names_are_lowercase_and_cover_the_staples():
    assert "armageddon" in MASS_LAND_DENIAL_NAMES
    assert "winter orb" in MASS_LAND_DENIAL_NAMES
    assert all(name == name.lower() for name in MASS_LAND_DENIAL_NAMES)


def test_extra_turn_text_matches_the_printed_wording():
    assert EXTRA_TURN_TEXT in "take an extra turn after this one."


def test_bracket_labels_name_all_five_tiers():
    assert BRACKET_LABELS == {
        1: "Exhibition",
        2: "Core",
        3: "Upgraded",
        4: "Optimized",
        5: "cEDH",
    }
