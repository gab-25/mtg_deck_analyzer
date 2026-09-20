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


from mtg_deck_analyzer.domain.mana import cards_seen, color_fixing, sources_required


class TestCardsSeen:
    def test_turn_one_is_the_opening_hand(self):
        assert cards_seen(1) == 7

    def test_one_more_card_per_turn_on_the_play(self):
        assert cards_seen(4) == 10

    def test_turn_zero_is_still_the_opening_hand(self):
        assert cards_seen(0) == 7


class TestSourcesRequired:
    def test_single_pip_on_turn_one(self):
        assert sources_required(1, 1, 99) == 27

    def test_double_pip_on_turn_two(self):
        assert sources_required(2, 2, 99) == 40

    def test_a_later_turn_asks_for_less(self):
        assert sources_required(1, 5, 99) < sources_required(1, 1, 99)

    def test_no_pips_needs_nothing(self):
        assert sources_required(0, 3, 99) == 0


class TestColorFixing:
    def _deck(self, *cards):
        return [{"quantity": 1, "is_commander": False, "data": c} for c in cards]

    def test_a_colorless_deck_reports_nothing(self):
        deck = self._deck(_card("{2}", type_line="Artifact", cmc=2.0))
        assert color_fixing(deck, 99) == []

    def test_the_hardest_cast_drives_the_requirement(self):
        # A {U}{U} two-drop is harder to cast on curve than a {U} five-drop.
        deck = self._deck(
            _card("{U}{U}", type_line="Instant", cmc=2.0),
            _card("{4}{U}", type_line="Sorcery", cmc=5.0),
        )
        blue = color_fixing(deck, 99)[0]
        assert blue["color"] == "U"
        assert blue["demand_pips"] == 2
        assert blue["demand_turn"] == 2
        assert blue["required"] == 40

    def test_the_demanding_card_is_named(self):
        card = _card("{B}{B}{B}", type_line="Sorcery", cmc=3.0)
        card["name"] = "Sign in Blood"
        black = color_fixing(self._deck(card), 99)[0]
        assert black["demand_card"] == "Sign in Blood"

    def test_pips_and_sources_are_reported_side_by_side(self):
        deck = self._deck(
            _card("{U}{U}", type_line="Instant", cmc=2.0),
            _card(type_line="Basic Land — Island", produced=["U"]),
        )
        blue = color_fixing(deck, 99)[0]
        assert blue["pips"] == 2
        assert blue["sources"] == 1

    def test_the_shortfall_is_the_gap_to_close(self):
        deck = self._deck(_card("{U}", type_line="Instant", cmc=1.0))
        blue = color_fixing(deck, 99)[0]
        assert blue["shortfall"] == blue["required"]

    def test_enough_sources_leave_no_shortfall(self):
        deck = self._deck(_card("{U}", type_line="Instant", cmc=1.0)) + [
            {"quantity": 40, "is_commander": False,
             "data": _card(type_line="Basic Land — Island", produced=["U"])}
        ]
        blue = color_fixing(deck, 99)[0]
        assert blue["sources"] == 40
        assert blue["shortfall"] == 0

    def test_a_color_with_only_sources_is_still_reported(self):
        # An off-color land with no spell asking for it: worth seeing.
        deck = self._deck(_card(type_line="Land", produced=["R"]))
        red = color_fixing(deck, 99)[0]
        assert red["color"] == "R"
        assert red["pips"] == 0
        assert red["required"] == 0

    def test_colors_come_back_in_wubrg_order(self):
        deck = self._deck(
            _card("{G}", type_line="Instant", cmc=1.0),
            _card("{W}", type_line="Instant", cmc=1.0),
        )
        assert [entry["color"] for entry in color_fixing(deck, 99)] == ["W", "G"]

    def test_the_commander_counts_as_a_requirement(self):
        deck = [{"quantity": 1, "is_commander": True,
                 "data": _card("{W}{U}{B}{R}{G}",
                               type_line="Legendary Creature — Angel", cmc=5.0)}]
        assert len(color_fixing(deck, 99)) == 5
