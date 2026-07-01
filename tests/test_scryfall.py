"""Tests for Scryfall data-processing helpers (no network access)."""

from mtg_deck_analyzer.integrations.scryfall import (
    _derive_text_source,
    _extract_price_eur,
    find_best_translated_card,
    get_face_details,
    is_text_untranslated,
    process_cached_card,
)


class _NoImageCache:
    """Minimal cache stub that reports no images (so nothing is downloaded)."""

    def has_image(self, name):
        return False


class TestExtractPriceEur:
    def test_uses_eur(self):
        assert _extract_price_eur({"prices": {"eur": "12.50"}}) == 12.50

    def test_falls_back_to_eur_foil(self):
        assert _extract_price_eur({"prices": {"eur_foil": "30.0"}}) == 30.0

    def test_converts_usd_when_no_eur(self):
        assert _extract_price_eur({"prices": {"usd": "10.00"}}) == 10.0 * 0.93

    def test_converts_usd_foil_when_only_foil_usd(self):
        result = _extract_price_eur({"prices": {"usd_foil": "10.00"}})
        assert result == 10.0 * 0.93

    def test_missing_prices_returns_zero(self):
        assert _extract_price_eur({}) == 0.0

    def test_invalid_eur_falls_through(self):
        assert _extract_price_eur({"prices": {"eur": "n/a", "usd": "5.00"}}) == 5.0 * 0.93

    def test_eur_preferred_over_usd(self):
        prices = {"prices": {"eur": "1.00", "usd": "100.00"}}
        assert _extract_price_eur(prices) == 1.00


class TestGetFaceDetails:
    def test_prefers_printed_fields(self):
        face = {
            "printed_name": "Lampo",
            "name": "Lightning Bolt",
            "printed_type_line": "Istantaneo",
            "type_line": "Instant",
            "printed_text": "Infligge 3 danni",
            "oracle_text": "Deal 3 damage",
            "mana_cost": "{R}",
        }
        details = get_face_details(face)
        assert details == {
            "name": "Lampo",
            "mana_cost": "{R}",
            "type_line": "Istantaneo",
            "rules_text": "Infligge 3 danni",
        }

    def test_falls_back_to_english_fields(self):
        face = {
            "name": "Lightning Bolt",
            "type_line": "Instant",
            "oracle_text": "Deal 3 damage",
        }
        details = get_face_details(face)
        assert details["name"] == "Lightning Bolt"
        assert details["type_line"] == "Instant"
        assert details["rules_text"] == "Deal 3 damage"
        assert details["mana_cost"] == ""

    def test_strips_whitespace(self):
        details = get_face_details({"name": "  Bolt  ", "mana_cost": " {R} "})
        assert details["name"] == "Bolt"
        assert details["mana_cost"] == "{R}"

    def test_empty_input(self):
        details = get_face_details({})
        assert details == {
            "name": "",
            "mana_cost": "",
            "type_line": "",
            "rules_text": "",
        }


class TestIsTextUntranslated:
    def test_single_face_translated(self):
        card = {"printed_text": "Infligge 3 danni", "oracle_text": "Deal 3 damage"}
        assert is_text_untranslated(card) is False

    def test_single_face_missing_printed(self):
        card = {"oracle_text": "Deal 3 damage"}
        assert is_text_untranslated(card) is True

    def test_single_face_identical_text(self):
        card = {"printed_text": "Deal 3 damage", "oracle_text": "Deal 3 damage"}
        assert is_text_untranslated(card) is True

    def test_single_face_no_oracle_text(self):
        # No oracle text at all -> nothing to translate.
        assert is_text_untranslated({"printed_text": ""}) is False

    def test_multi_face_one_untranslated(self):
        card = {
            "card_faces": [
                {"printed_text": "Tradotto", "oracle_text": "Translated"},
                {"oracle_text": "Untranslated"},
            ]
        }
        assert is_text_untranslated(card) is True

    def test_multi_face_all_translated(self):
        card = {
            "card_faces": [
                {"printed_text": "Uno", "oracle_text": "One"},
                {"printed_text": "Due", "oracle_text": "Two"},
            ]
        }
        assert is_text_untranslated(card) is False


class TestFindBestTranslatedCard:
    def test_empty_returns_none(self):
        assert find_best_translated_card([], "it") is None

    def test_returns_first_translated(self):
        prints = [
            {"printed_text": "Deal 3 damage", "oracle_text": "Deal 3 damage"},  # untranslated
            {"printed_text": "Infligge 3 danni", "oracle_text": "Deal 3 damage"},  # translated
        ]
        result = find_best_translated_card(prints, "it")
        assert result is prints[1]

    def test_falls_back_to_first_when_none_translated(self):
        prints = [
            {"printed_text": "Deal 3 damage", "oracle_text": "Deal 3 damage"},
            {"oracle_text": "Deal 3 damage"},
        ]
        result = find_best_translated_card(prints, "it")
        assert result is prints[0]


class TestTextSource:
    def test_process_cached_card_passes_text_source(self):
        card = {"id": "x", "name": "Foresta", "_text_source": "machine"}
        out = process_cached_card(card, _NoImageCache())
        assert out["text_source"] == "machine"

    def test_process_cached_card_missing_source_is_none(self):
        out = process_cached_card({"id": "x", "name": "Forest"}, _NoImageCache())
        assert out["text_source"] is None

    def test_derive_english_is_official(self):
        assert _derive_text_source({"oracle_text": "Deal 3 damage"}, "en") == "official"

    def test_derive_untranslated_non_english_is_english(self):
        card = {"oracle_text": "Deal 3 damage"}  # no printed_text -> untranslated
        assert _derive_text_source(card, "it") == "english"

    def test_derive_translated_non_english_is_official(self):
        card = {"printed_text": "Infligge 3 danni", "oracle_text": "Deal 3 damage"}
        assert _derive_text_source(card, "it") == "official"
