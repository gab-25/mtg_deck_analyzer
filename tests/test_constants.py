"""Tests for the unified language registry."""

from mtg_deck_analyzer.domain.constants import (
    LANG_DISPLAY_NAMES,
    LANG_MAP,
    LANGUAGES,
    normalize_lang,
)


def test_derived_maps_match_registry_keys():
    assert set(LANG_MAP) == set(LANGUAGES)
    assert set(LANG_DISPLAY_NAMES) == set(LANGUAGES)


def test_derived_maps_use_registry_values():
    assert LANG_MAP["it"] == "Italian"
    assert LANG_DISPLAY_NAMES["it"] == "Italiano"


def test_normalize_lang_lowercases_known_code():
    assert normalize_lang("IT") == "it"
    assert normalize_lang("en") == "en"


def test_normalize_lang_falls_back_to_default():
    assert normalize_lang("xx") == "en"
    assert normalize_lang("") == "en"
    assert normalize_lang(None) == "en"
