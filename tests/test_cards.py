"""Tests for card classification."""

from mtg_deck_analyzer.domain.cards import classify_card, compute_statistics


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


class TestClassifyDoubleFacedCard:
    """A double-faced card is played as its front face, so that face decides."""

    def _dfc(self, front, back):
        return {
            "type_line": f"{front} // {back}",
            "faces": [{"type_line": front}, {"type_line": back}],
        }

    def test_spell_with_a_land_back_is_the_spell(self):
        # Sink into Stupor // Soporific Springs.
        assert classify_card(self._dfc("Instant", "Land")) == "Instant"

    def test_creature_with_a_land_back_is_a_creature(self):
        # Kazandu Mammoth // Kazandu Valley.
        card = self._dfc("Creature — Elephant", "Land")
        assert classify_card(card) == "Creature"

    def test_land_front_stays_a_land(self):
        card = self._dfc("Land", "Creature — Elemental")
        assert classify_card(card) == "Land"

    def test_combined_type_line_alone_is_split_on_the_slashes(self):
        # Decks stored before the faces carried their own type line.
        assert classify_card({"type_line": "Sorcery // Land"}) == "Sorcery"

    def test_adventure_is_its_creature_half(self):
        # Brazen Borrower // Petty Theft.
        card = self._dfc("Creature — Faerie Rogue", "Instant — Adventure")
        assert classify_card(card) == "Creature"


class TestComputeStatistics:
    def test_a_spell_with_a_land_back_is_counted_as_a_spell(self):
        cards = [
            {
                "quantity": 1,
                "data": {
                    "type_line": "Instant // Land",
                    "faces": [{"type_line": "Instant"}, {"type_line": "Land"}],
                    "cmc": 3.0,
                },
            },
            {
                "quantity": 1,
                "data": {"type_line": "Basic Land — Island", "cmc": 0.0},
            },
        ]
        total_cards, _total_price, counts = compute_statistics(cards)
        assert total_cards == 2
        assert counts["Instant"] == 1
        assert counts["Land"] == 1
