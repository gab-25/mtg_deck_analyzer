"""Tests for pip counting, colored sources and the mana curve."""

from mtg_deck_analyzer.domain.mana import (
    card_pips,
    deck_pips,
    deck_sources,
    mana_curve,
    produced_colors,
)


def _card(mana_cost="", type_line="Creature — Elf", produced=None, cmc=0.0):
    data = {
        "name": "Test Card",
        "type_line": type_line,
        "cmc": cmc,
        "faces": [{"name": "Test Card", "mana_cost": mana_cost,
                   "type_line": type_line, "rules_text": ""}],
    }
    if produced is not None:
        data["produced_mana"] = produced
    return data


def _item(card, quantity=1, is_commander=False):
    return {"quantity": quantity, "is_commander": is_commander, "data": card}


class TestCardPips:
    def test_generic_mana_is_not_a_pip(self):
        assert card_pips(_card("{3}")) == {"W": 0, "U": 0, "B": 0, "R": 0, "G": 0}

    def test_each_colored_symbol_counts_once(self):
        assert card_pips(_card("{1}{U}{U}"))["U"] == 2

    def test_hybrid_counts_for_both_colors(self):
        pips = card_pips(_card("{W/U}"))
        assert pips["W"] == 1
        assert pips["U"] == 1

    def test_monocolor_hybrid_counts_for_its_color(self):
        assert card_pips(_card("{2/B}"))["B"] == 1

    def test_phyrexian_counts_for_its_color(self):
        assert card_pips(_card("{G/P}"))["G"] == 1

    def test_x_and_colorless_are_not_pips(self):
        assert card_pips(_card("{X}{C}")) == {"W": 0, "U": 0, "B": 0, "R": 0, "G": 0}

    def test_both_halves_of_a_split_card_count(self):
        # Fire // Ice.
        card = {
            "faces": [
                {"mana_cost": "{1}{R}", "type_line": "Instant"},
                {"mana_cost": "{1}{U}", "type_line": "Instant"},
            ]
        }
        assert card_pips(card)["R"] == 1
        assert card_pips(card)["U"] == 1

    def test_a_costless_back_face_adds_nothing(self):
        card = {
            "faces": [
                {"mana_cost": "{2}{G}", "type_line": "Creature — Human"},
                {"mana_cost": "", "type_line": "Creature — Werewolf"},
            ]
        }
        assert card_pips(card)["G"] == 1


class TestDeckPips:
    def test_pips_are_weighted_by_quantity(self):
        deck = [_item(_card("{B}{B}"), quantity=3)]
        assert deck_pips(deck)["B"] == 6

    def test_the_commander_counts(self):
        deck = [_item(_card("{W}{U}"), is_commander=True)]
        assert deck_pips(deck)["W"] == 1
        assert deck_pips(deck)["U"] == 1


class TestProducedColors:
    def test_a_land_taps_for_what_it_produces(self):
        card = _card(type_line="Land", produced=["W", "U"])
        assert produced_colors(card) == ["W", "U"]

    def test_colorless_production_is_not_a_color(self):
        card = _card(type_line="Artifact", produced=["C"])
        assert produced_colors(card) == []

    def test_a_mana_dork_is_a_source(self):
        card = _card(type_line="Creature — Elf Druid", produced=["G"])
        assert produced_colors(card) == ["G"]

    def test_a_one_shot_ritual_is_not_a_source(self):
        # Dark Ritual makes mana but never sits on the battlefield.
        card = _card(type_line="Instant", produced=["B"])
        assert produced_colors(card) == []

    def test_a_modal_card_with_a_land_back_is_a_source(self):
        # Agadeem's Awakening // Agadeem, the Undercrypt.
        card = {
            "type_line": "Sorcery // Land",
            "produced_mana": ["B"],
            "faces": [{"type_line": "Sorcery"}, {"type_line": "Land"}],
        }
        assert produced_colors(card) == ["B"]

    def test_results_are_in_wubrg_order(self):
        card = _card(type_line="Land", produced=["G", "W", "B"])
        assert produced_colors(card) == ["W", "B", "G"]

    def test_a_card_stored_before_produced_mana_has_no_sources(self):
        assert produced_colors(_card(type_line="Land")) == []


class TestDeckSources:
    def test_sources_are_weighted_by_quantity(self):
        deck = [_item(_card(type_line="Basic Land — Island", produced=["U"]), 10)]
        assert deck_sources(deck)["U"] == 10

    def test_the_commander_is_not_a_source(self):
        # It is never in the library, so it can never be drawn as fixing.
        deck = [_item(_card(type_line="Legendary Creature — Elf",
                            produced=["G"]), is_commander=True)]
        assert deck_sources(deck)["G"] == 0


class TestManaCurve:
    def test_lands_are_excluded(self):
        deck = [_item(_card(type_line="Basic Land — Forest", cmc=0.0), 38)]
        assert mana_curve(deck) == [0] * 8

    def test_cards_land_in_their_mana_value_bucket(self):
        deck = [_item(_card(cmc=2.0), 3), _item(_card(cmc=5.0), 1)]
        curve = mana_curve(deck)
        assert curve[2] == 3
        assert curve[5] == 1

    def test_everything_from_seven_up_is_merged(self):
        deck = [_item(_card(cmc=7.0)), _item(_card(cmc=12.0))]
        assert mana_curve(deck)[7] == 2

    def test_a_spell_with_a_land_back_stays_on_the_curve(self):
        card = {
            "type_line": "Instant // Land",
            "cmc": 3.0,
            "faces": [{"type_line": "Instant"}, {"type_line": "Land"}],
        }
        assert mana_curve([_item(card)])[3] == 1
