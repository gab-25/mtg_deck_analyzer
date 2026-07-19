"""Tests for Scryfall data-processing helpers (no network access)."""

from mtg_deck_analyzer.integrations import scryfall
from mtg_deck_analyzer.integrations.scryfall import (
    _derive_text_source,
    _extract_price_eur,
    _resolve_english_name,
    find_best_translated_card,
    get_face_details,
    is_text_untranslated,
    process_cached_card,
)


class _FakeResponse:
    """Minimal stand-in for a ``requests`` response used to stub Scryfall calls."""

    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


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


class TestResolveEnglishName:
    def test_returns_english_name_from_printed_name_match(self, monkeypatch):
        captured = {}

        def fake_get(url):
            captured["url"] = url
            return _FakeResponse(200, {"data": [{"name": "Lightning Bolt"}]})

        monkeypatch.setattr(scryfall, "_scryfall_get", fake_get)
        assert _resolve_english_name("Fulmine", "it") == "Lightning Bolt"
        # The query must be scoped to the requested language and exact-matched.
        assert 'lang%3Ait' in captured["url"]

    def test_returns_none_when_no_match(self, monkeypatch):
        monkeypatch.setattr(
            scryfall, "_scryfall_get", lambda url: _FakeResponse(200, {"data": []})
        )
        assert _resolve_english_name("Nonexistent", "it") is None

    def test_returns_none_on_error_status(self, monkeypatch):
        monkeypatch.setattr(
            scryfall, "_scryfall_get", lambda url: _FakeResponse(404)
        )
        assert _resolve_english_name("Fulmine", "it") is None

    def test_returns_none_when_request_fails(self, monkeypatch):
        monkeypatch.setattr(scryfall, "_scryfall_get", lambda url: None)
        assert _resolve_english_name("Fulmine", "it") is None


class _DictCache:
    """In-memory cache backend stub (no images)."""

    def __init__(self):
        self.cards = {}

    def get_card(self, key):
        return self.cards.get(key)

    def set_card(self, key, value):
        self.cards[key] = value

    def has_image(self, name):
        return False


class TestForeignNameFallback:
    def test_foreign_name_resolves_via_search_then_english_lookup(self, monkeypatch):
        # An English localized-text print so no Gemini translation is triggered.
        card_json = {
            "id": "abc",
            "name": "Lightning Bolt",
            "lang": "it",
            "printed_name": "Fulmine",
            "printed_text": "Infligge 3 danni a qualsiasi bersaglio.",
            "oracle_text": "Lightning Bolt deals 3 damage to any target.",
            "set": "lea",
            "collector_number": "161",
            "prices": {"eur": "1.00"},
        }

        calls = []

        def fake_get(url):
            calls.append(url)
            if "cards/named" in url and "Fulmine" in url:
                # First exact English lookup fails: the name is Italian.
                return _FakeResponse(404)
            if "cards/search" in url:
                return _FakeResponse(200, {"data": [{"name": "Lightning Bolt"}]})
            if "cards/named" in url and "Lightning" in url:
                # Retry with the resolved English name succeeds.
                return _FakeResponse(200, card_json)
            # Localized print lookup by set/collector.
            return _FakeResponse(200, card_json)

        monkeypatch.setattr(scryfall, "_scryfall_get", fake_get)

        result = scryfall.fetch_card_data("Fulmine", "it", _DictCache())

        assert result is not None
        assert result["name"] == "Fulmine"
        assert result["price_eur"] == 1.00
        # The search fallback must have been exercised.
        assert any("cards/search" in url for url in calls)

    def test_unknown_foreign_name_caches_not_found(self, monkeypatch):
        def fake_get(url):
            if "cards/search" in url:
                return _FakeResponse(200, {"data": []})
            return _FakeResponse(404)

        monkeypatch.setattr(scryfall, "_scryfall_get", fake_get)
        cache = _DictCache()

        result = scryfall.fetch_card_data("Inesistente", "it", cache)

        assert result is None
        assert cache.cards["card_it_inesistente"] == {"error": "not_found"}
