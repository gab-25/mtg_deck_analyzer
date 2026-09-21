"""Tests for pip counting, colored sources and the mana curve."""

import pytest

from mtg_deck_analyzer.domain.mana import (
    card_pips,
    deck_pips,
    mana_curve,
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


class TestManaCurve:
    def test_lands_are_excluded(self):
        deck = [_item(_card(type_line="Basic Land — Forest", cmc=0.0), 38)]
        curve = mana_curve(deck)
        assert all(b["permanents"] == 0 and b["spells"] == 0 for b in curve)

    def test_permanents_and_spells_are_separated(self):
        deck = [
            _item(_card(type_line="Creature — Bear", cmc=2.0), 3),
            _item(_card(type_line="Instant", cmc=2.0), 4),
        ]
        assert mana_curve(deck)[2] == {"permanents": 3, "spells": 4}

    def test_artifacts_enchantments_and_planeswalkers_are_permanents(self):
        for type_line in ("Artifact", "Enchantment — Aura",
                          "Legendary Planeswalker — Jace", "Battle — Siege"):
            deck = [_item(_card(type_line=type_line, cmc=3.0))]
            assert mana_curve(deck)[3]["permanents"] == 1, type_line

    def test_sorceries_are_spells(self):
        deck = [_item(_card(type_line="Sorcery", cmc=1.0))]
        assert mana_curve(deck)[1] == {"permanents": 0, "spells": 1}

    def test_everything_from_seven_up_is_merged(self):
        deck = [_item(_card(type_line="Sorcery", cmc=7.0)),
                _item(_card(type_line="Sorcery", cmc=12.0))]
        assert mana_curve(deck)[7]["spells"] == 2

    def test_the_commander_is_included(self):
        # It is a card you cast every game, so it belongs on the curve. Checked
        # against Moxfield: a deck whose only six-drop is its commander shows a
        # bar of one at six, not an empty bucket.
        deck = [_item(_card(type_line="Legendary Creature — Elf", cmc=3.0),
                      is_commander=True)]
        assert mana_curve(deck)[3]["permanents"] == 1

    def test_a_spell_with_a_land_back_stays_on_the_curve(self):
        card = {"type_line": "Instant // Land", "cmc": 3.0,
                "faces": [{"type_line": "Instant"}, {"type_line": "Land"}]}
        assert mana_curve([_item(card)])[3]["spells"] == 1


from mtg_deck_analyzer.domain.mana import cards_seen


class TestCardsSeen:
    def test_turn_one_is_the_opening_hand(self):
        assert cards_seen(1) == 7

    def test_one_more_card_per_turn_on_the_play(self):
        assert cards_seen(4) == 10

    def test_turn_zero_is_still_the_opening_hand(self):
        assert cards_seen(0) == 7


from mtg_deck_analyzer.domain.mana import is_land_card, land_production


class TestIsLandCard:
    def test_a_plain_land_is_a_land(self):
        assert is_land_card({"type_line": "Basic Land — Island",
                             "faces": [{"type_line": "Basic Land — Island"}]})

    def test_a_spell_with_a_land_back_is_a_land_here(self):
        # Sink into Stupor // Soporific Springs: counted as a land for the
        # mana block, even though classify_card files it as an Instant.
        card = {"type_line": "Instant // Land",
                "faces": [{"type_line": "Instant"}, {"type_line": "Land"}]}
        assert is_land_card(card)

    def test_a_creature_with_a_land_back_is_a_land_here(self):
        card = {"type_line": "Creature — Weird // Land",
                "faces": [{"type_line": "Creature — Weird"}, {"type_line": "Land"}]}
        assert is_land_card(card)

    def test_a_mana_rock_is_not_a_land(self):
        assert not is_land_card({"type_line": "Artifact",
                                 "faces": [{"type_line": "Artifact"}]})


class TestLandProduction:
    def _land(self, name, produced, type_line="Land"):
        return {"name": name, "type_line": type_line, "produced_mana": produced,
                "faces": [{"type_line": type_line}]}

    def _item(self, data, quantity=1):
        return {"quantity": quantity, "is_commander": False, "data": data}

    def test_counts_lands_and_their_color_slots(self):
        deck = [
            self._item(self._land("Island", ["U"]), 10),
            self._item(self._land("Command Tower", ["W", "U", "B", "R", "G"])),
        ]
        out = land_production(deck)
        assert out["lands"] == 11
        # Ten one-colour lands plus one that fills five slots.
        assert out["symbol_slots"] == 15
        assert out["by_color"]["U"] == 11
        assert out["by_color"]["G"] == 1

    def test_a_colorless_land_fills_a_colorless_slot(self):
        deck = [self._item(self._land("Wastes", ["C"]))]
        out = land_production(deck)
        assert out["symbol_slots"] == 1
        assert out["by_color"]["C"] == 1

    def test_a_land_that_produces_nothing_adds_no_slot(self):
        deck = [self._item(self._land("Maze of Ith", []))]
        out = land_production(deck)
        assert out["lands"] == 1
        assert out["symbol_slots"] == 0

    def test_a_mana_rock_is_not_counted(self):
        rock = {"name": "Sol Ring", "type_line": "Artifact",
                "produced_mana": ["C"], "faces": [{"type_line": "Artifact"}]}
        out = land_production([self._item(rock)])
        assert out["lands"] == 0
        assert out["by_color"]["C"] == 0

    def test_a_spell_with_a_land_back_counts_as_a_land(self):
        card = {"name": "Sink into Stupor", "type_line": "Instant // Land",
                "produced_mana": ["U"],
                "faces": [{"type_line": "Instant"}, {"type_line": "Land"}]}
        out = land_production([self._item(card)])
        assert out["lands"] == 1
        assert out["by_color"]["U"] == 1


from mtg_deck_analyzer.domain.mana import mana_value_summary


class TestManaValueSummary:
    def test_an_empty_deck_is_all_zeroes(self):
        out = mana_value_summary([])
        assert out == {"total": 0, "average": 0.0, "average_without_lands": 0.0,
                       "median": 0.0, "median_without_lands": 0.0}

    def test_totals_and_averages_are_quantity_weighted(self):
        deck = [_item(_card(type_line="Sorcery", cmc=3.0), 3),
                _item(_card(type_line="Basic Land — Island", cmc=0.0), 1)]
        out = mana_value_summary(deck)
        assert out["total"] == 9
        assert out["average"] == pytest.approx(9 / 4)
        assert out["average_without_lands"] == pytest.approx(3.0)

    def test_medians_are_reported_with_and_without_lands(self):
        deck = [_item(_card(type_line="Sorcery", cmc=4.0), 1),
                _item(_card(type_line="Basic Land — Island", cmc=0.0), 3)]
        out = mana_value_summary(deck)
        assert out["median"] == 0.0
        assert out["median_without_lands"] == 4.0

    def test_the_commander_is_excluded(self):
        # Moxfield's figures are main-deck only; the reference deck totals 156
        # over 98 cards, not 160 over 100.
        deck = [_item(_card(type_line="Sorcery", cmc=2.0)),
                _item(_card(type_line="Legendary Creature — Elf", cmc=6.0),
                      is_commander=True)]
        assert mana_value_summary(deck)["total"] == 2

    def test_a_deck_of_only_lands_has_no_non_land_average(self):
        deck = [_item(_card(type_line="Basic Land — Island", cmc=0.0), 5)]
        out = mana_value_summary(deck)
        assert out["average_without_lands"] == 0.0
        assert out["median_without_lands"] == 0.0


from mtg_deck_analyzer.domain.mana import color_card_counts, color_curves


def _identity(colors, type_line="Creature — Bear", cmc=2.0):
    return {"name": "X", "type_line": type_line, "cmc": cmc,
            "color_identity": list(colors),
            "faces": [{"name": "X", "mana_cost": "", "type_line": type_line,
                       "rules_text": ""}]}


class TestColorCardCounts:
    def test_counts_cards_by_color_identity(self):
        deck = [_item(_identity("U"), 3), _item(_identity("WU"))]
        out = color_card_counts(deck)
        assert out["non_lands"] == 4
        assert out["by_color"]["U"] == 4
        assert out["by_color"]["W"] == 1
        assert out["by_color"]["B"] == 0

    def test_lands_are_excluded_from_both_sides(self):
        deck = [_item(_identity("U", type_line="Land", cmc=0.0), 5),
                _item(_identity("U"))]
        out = color_card_counts(deck)
        assert out["non_lands"] == 1
        assert out["by_color"]["U"] == 1

    def test_the_commander_is_counted(self):
        # Unlike the mana-value figures, the colour split includes it.
        deck = [_item(_identity("R"), is_commander=True)]
        out = color_card_counts(deck)
        assert out["non_lands"] == 1
        assert out["by_color"]["R"] == 1


class TestColorCurves:
    def test_a_color_curve_counts_only_that_colors_cards(self):
        deck = [_item(_identity("U", cmc=1.0), 2), _item(_identity("R", cmc=3.0))]
        curves = color_curves(deck)
        assert curves["U"][1] == 2
        assert curves["U"][3] == 0
        assert curves["R"][3] == 1

    def test_a_multicolor_card_appears_in_every_colors_curve(self):
        curves = color_curves([_item(_identity("WU", cmc=2.0))])
        assert curves["W"][2] == 1
        assert curves["U"][2] == 1

    def test_lands_are_excluded(self):
        deck = [_item(_identity("G", type_line="Land", cmc=0.0), 4)]
        assert sum(color_curves(deck)["G"]) == 0

    def test_seven_and_up_is_merged(self):
        deck = [_item(_identity("B", cmc=9.0))]
        assert color_curves(deck)["B"][7] == 1

    def test_every_color_has_a_curve_even_when_empty(self):
        curves = color_curves([])
        assert set(curves) == set("WUBRG")
        assert all(len(c) == 8 for c in curves.values())


class TestMirrorLands:
    """Lands that produce whatever your other lands produce make nothing of
    their own, so crediting them with five colours double-counts the mana the
    rest of the mana base already supplies.

    Reflecting Pool and Cactus Preserve read "any type that a land you control
    could produce". A land reading "a land an opponent controls" (Exotic
    Orchard) is different: what it makes is unknowable from the decklist, so
    it keeps its colours — which is also what Moxfield does.
    """

    def _land(self, name, text, produced):
        return {"quantity": 1, "is_commander": False, "data": {
            "name": name, "type_line": "Land", "produced_mana": produced,
            "faces": [{"name": name, "type_line": "Land", "mana_cost": "",
                       "rules_text": text}]}}

    def test_a_mirror_land_still_counts_as_a_land(self):
        deck = [self._land("Reflecting Pool",
                           "{T}: Add one mana of any type that a land you "
                           "control could produce.", list("WUBRG"))]
        assert land_production(deck)["lands"] == 1

    def test_a_mirror_land_contributes_no_colour(self):
        deck = [self._land("Reflecting Pool",
                           "{T}: Add one mana of any type that a land you "
                           "control could produce.", list("WUBRG"))]
        out = land_production(deck)
        assert out["symbol_slots"] == 0
        assert all(v == 0 for v in out["by_color"].values())

    def test_a_land_mirroring_an_opponent_keeps_its_colours(self):
        deck = [self._land("Exotic Orchard",
                           "{T}: Add one mana of any color that a land an "
                           "opponent controls could produce.", list("WUBRG"))]
        assert land_production(deck)["symbol_slots"] == 5

    def test_a_land_that_genuinely_produces_keeps_its_colours(self):
        # Command Tower names the colours it makes rather than borrowing them.
        deck = [self._land("Command Tower",
                           "{T}: Add one mana of any color in your commander's "
                           "color identity.", list("WUBRG"))]
        assert land_production(deck)["symbol_slots"] == 5
