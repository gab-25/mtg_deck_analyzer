"""Tests for Scryfall data-processing helpers (no network access)."""

from mtg_deck_analyzer.integrations.scryfall import (
    _extract_price_eur,
    get_face_details,
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
    def test_reads_english_fields(self):
        face = {
            "name": "Lightning Bolt",
            "type_line": "Instant",
            "oracle_text": "Deal 3 damage",
            "mana_cost": "{R}",
        }
        details = get_face_details(face)
        assert details == {
            "name": "Lightning Bolt",
            "mana_cost": "{R}",
            "type_line": "Instant",
            "rules_text": "Deal 3 damage",
        }

    def test_missing_fields_default_empty(self):
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


class TestProcessCachedCard:
    def test_uses_english_name(self):
        out = process_cached_card({"id": "x", "name": "Forest"}, _NoImageCache())
        assert out["name"] == "Forest"

    def test_missing_name_falls_back(self):
        out = process_cached_card({"id": "x"}, _NoImageCache())
        assert out["name"] == "Unknown Card"

    def test_carries_the_legalities_through(self):
        card = {"id": "x", "name": "Black Lotus", "legalities": {"commander": "banned"}}
        out = process_cached_card(card, _NoImageCache())
        assert out["legalities"] == {"commander": "banned"}

    def test_missing_legalities_becomes_an_empty_dict(self):
        out = process_cached_card({"id": "x", "name": "Forest"}, _NoImageCache())
        assert out["legalities"] == {}

    def test_carries_the_game_changer_flag_through(self):
        card = {"id": "x", "name": "Rhystic Study", "game_changer": True}
        out = process_cached_card(card, _NoImageCache())
        assert out["game_changer"] is True

    def test_carries_a_present_false_game_changer_flag_through(self):
        card = {"id": "x", "name": "Forest", "game_changer": False}
        out = process_cached_card(card, _NoImageCache())
        assert out["game_changer"] is False

    def test_missing_game_changer_stays_unknown(self):
        # None (key absent) is distinct from an explicit False: only the
        # unknown case lets the bracket estimate fall back to the name list.
        out = process_cached_card({"id": "x", "name": "Forest"}, _NoImageCache())
        assert out["game_changer"] is None

class TestProducedMana:
    """``produced_mana`` drives the deck's colored-source count."""

    def test_produced_mana_is_carried_through(self):
        card = {
            "id": "x",
            "name": "Command Tower",
            "type_line": "Land",
            "produced_mana": ["W", "U", "B", "R", "G"],
        }
        processed = process_cached_card(card, _NoImageCache())
        assert processed["produced_mana"] == ["W", "U", "B", "R", "G"]

    def test_missing_produced_mana_is_an_empty_list(self):
        card = {"id": "x", "name": "Lightning Bolt", "type_line": "Instant"}
        assert process_cached_card(card, _NoImageCache())["produced_mana"] == []
