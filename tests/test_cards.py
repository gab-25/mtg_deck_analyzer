"""Tests for card classification and deck-type inference."""

from mtg_deck_analyzer.domain.cards import classify_card, infer_deck_type


def _card(type_line):
    return {"type_line": type_line}


def _item(qty, type_line):
    return {"quantity": qty, "data": _card(type_line)}


class TestClassifyCard:
    def test_land(self):
        assert classify_card(_card("Basic Land — Forest")) == "Land"

    def test_creature(self):
        assert classify_card(_card("Creature — Goblin")) == "Creature"

    def test_planeswalker(self):
        assert classify_card(_card("Legendary Planeswalker — Jace")) == "Planeswalker"

    def test_instant(self):
        assert classify_card(_card("Instant")) == "Instant"

    def test_sorcery(self):
        assert classify_card(_card("Sorcery")) == "Sorcery"

    def test_artifact(self):
        assert classify_card(_card("Artifact")) == "Artifact"

    def test_enchantment(self):
        assert classify_card(_card("Enchantment — Aura")) == "Enchantment"

    def test_battle(self):
        assert classify_card(_card("Battle — Siege")) == "Battle"

    def test_unknown_is_other(self):
        assert classify_card(_card("Dungeon")) == "Other"

    def test_empty_is_other(self):
        assert classify_card(_card("")) == "Other"

    def test_land_takes_precedence_over_creature(self):
        # A creature-land's type line contains both; "land" is checked first.
        assert classify_card(_card("Land Creature — Elemental")) == "Land"

    def test_falls_back_to_face_type_line(self):
        card = {"faces": [{"type_line": "Creature — Beast"}]}
        assert classify_card(card) == "Creature"


class TestInferDeckType:
    def test_commander_singleton_100(self):
        cards = [_item(1, "Creature") for _ in range(63)]
        cards += [_item(1, "Land") for _ in range(37)]  # 100 total, singleton
        assert infer_deck_type(cards) == "Commander / EDH"

    def test_commander_allows_repeated_basic_lands(self):
        # Non-lands are singleton; lands repeat — still EDH at 100 cards.
        cards = [_item(1, "Creature") for _ in range(64)]
        cards.append(_item(36, "Land"))  # 64 + 36 = 100
        assert infer_deck_type(cards) == "Commander / EDH"

    def test_constructed_60_plus(self):
        cards = [_item(4, "Creature") for _ in range(15)]  # 60 total, playsets
        assert infer_deck_type(cards) == "Constructed"

    def test_limited_40_to_59(self):
        cards = [_item(1, "Creature") for _ in range(23)]
        cards += [_item(1, "Land") for _ in range(17)]  # 40 total
        assert infer_deck_type(cards) == "Limited"

    def test_custom_small_deck(self):
        cards = [_item(1, "Creature") for _ in range(10)]
        assert infer_deck_type(cards) == "Custom"

    def test_100_cards_with_playsets_is_constructed_not_edh(self):
        # 100 cards but non-singleton -> falls through to Constructed.
        cards = [_item(4, "Creature") for _ in range(25)]
        assert infer_deck_type(cards) == "Constructed"
