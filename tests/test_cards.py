"""Tests for card classification."""

from mtg_deck_analyzer.domain.cards import classify_card


def _card(type_line):
    return {"type_line": type_line}


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
