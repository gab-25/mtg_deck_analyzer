"""Tests for the functional tagging of cards by the role they play."""

from mtg_deck_analyzer.domain.cards import rules_text
from mtg_deck_analyzer.domain.roles import (
    baseline_report,
    card_roles,
    interaction_count,
    role_counts,
)


def _card(text, type_line="Instant", name="Test Card"):
    return {
        "name": name,
        "type_line": type_line,
        "faces": [{"name": name, "type_line": type_line, "rules_text": text,
                   "mana_cost": ""}],
    }


def _item(card, quantity=1):
    return {"quantity": quantity, "is_commander": False, "data": card}


class TestRulesText:
    def test_every_face_is_included_and_lowercased(self):
        card = {"faces": [{"rules_text": "Flying"}, {"rules_text": "Draw A Card"}]}
        assert rules_text(card) == "flying\ndraw a card"

    def test_a_card_with_no_faces_has_no_text(self):
        assert rules_text({}) == ""


class TestRamp:
    def test_a_mana_rock_is_ramp(self):
        # Sol Ring.
        card = _card("{T}: Add {C}{C}.", "Artifact")
        assert "ramp" in card_roles(card)

    def test_a_mana_dork_is_ramp(self):
        card = _card("{T}: Add {G}.", "Creature — Elf Druid")
        assert "ramp" in card_roles(card)

    def test_land_fetch_is_ramp(self):
        # Cultivate.
        card = _card(
            "Search your library for up to two basic land cards, reveal them, "
            "put one onto the battlefield tapped and the other into your hand.",
            "Sorcery",
        )
        assert "ramp" in card_roles(card)

    def test_a_land_is_not_ramp(self):
        # A land is the mana, not what accelerates it.
        card = _card("{T}: Add {G}.", "Basic Land — Forest")
        assert "ramp" not in card_roles(card)


class TestDraw:
    def test_drawing_a_card_is_draw(self):
        assert "draw" in card_roles(_card("Draw a card."))

    def test_drawing_several_cards_is_draw(self):
        assert "draw" in card_roles(_card("Draw three cards."))

    def test_a_vanilla_creature_does_not_draw(self):
        assert "draw" not in card_roles(_card("Flying", "Creature — Bird"))

    def test_an_opponent_drawing_a_card_is_not_the_decks_draw(self):
        # Underworld Dreams: a punisher effect, not a draw source.
        card = _card(
            "Whenever an opponent draws a card, Underworld Dreams deals 1 "
            "damage to that player.",
            "Enchantment",
        )
        assert "draw" not in card_roles(card)

    def test_target_player_draws_is_draw(self):
        # Sign in Blood: "target player" is normally the caster.
        card = _card("Target player draws two cards and loses 2 life.")
        assert "draw" in card_roles(card)

    def test_each_player_draws_after_discarding_is_draw(self):
        # Wheel of Fortune: a symmetric wheel is still a draw source.
        card = _card(
            "Each player discards their hand, then draws seven cards.",
            "Sorcery",
        )
        assert "draw" in card_roles(card)

    def test_each_player_draws_cards_equal_to_is_draw(self):
        # Windfall.
        card = _card(
            "Each player discards their hand, then draws cards equal to the "
            "greatest number of cards a player discarded this way.",
            "Sorcery",
        )
        assert "draw" in card_roles(card)


class TestRemoval:
    def test_destroy_target_is_targeted_removal(self):
        assert "targeted_removal" in card_roles(_card("Destroy target creature."))

    def test_exile_target_is_targeted_removal(self):
        # Swords to Plowshares.
        roles = card_roles(_card("Exile target creature. Its controller gains life."))
        assert "targeted_removal" in roles

    def test_burn_to_any_target_is_targeted_removal(self):
        # Lightning Bolt.
        card = _card("Lightning Bolt deals 3 damage to any target.")
        assert "targeted_removal" in card_roles(card)

    def test_bounce_is_targeted_removal(self):
        card = _card("Return target creature to its owner's hand.")
        assert "targeted_removal" in card_roles(card)

    def test_destroy_all_is_a_board_wipe(self):
        # Wrath of God.
        card = _card("Destroy all creatures. They can't be regenerated.", "Sorcery")
        assert "board_wipe" in card_roles(card)

    def test_mass_damage_is_a_board_wipe(self):
        # Blasphemous Act.
        card = _card("Blasphemous Act deals 13 damage to each creature.", "Sorcery")
        assert "board_wipe" in card_roles(card)


class TestTutor:
    def test_searching_for_a_spell_is_a_tutor(self):
        # Demonic Tutor.
        card = _card("Search your library for a card, put it into your hand.")
        assert "tutor" in card_roles(card)

    def test_searching_only_for_lands_is_ramp_not_a_tutor(self):
        card = _card(
            "Search your library for a basic land card, put it onto the "
            "battlefield tapped.",
            "Sorcery",
        )
        roles = card_roles(card)
        assert "ramp" in roles
        assert "tutor" not in roles

    def test_fetching_a_named_basic_land_type_is_ramp_not_tutor(self):
        # Wood Elves-style ETB: names the type instead of saying "land".
        card = _card(
            "When this creature enters, search your library for a Forest "
            "card, reveal it, and put it into your hand.",
            "Creature — Elf Scout",
        )
        roles = card_roles(card)
        assert "ramp" in roles
        assert "tutor" not in roles

    def test_a_fetchland_naming_basic_types_is_not_a_tutor(self):
        # Windswept Heath: says "a Forest or Plains card", never "land".
        card = _card(
            "{T}, Pay 1 life, Sacrifice Windswept Heath: Search your "
            "library for a Forest or Plains card, put it onto the "
            "battlefield, then shuffle.",
            "Land",
        )
        assert "tutor" not in card_roles(card)


class TestInteraction:
    def test_a_counterspell_interacts(self):
        assert "interaction" in card_roles(_card("Counter target spell."))

    def test_granting_hexproof_interacts(self):
        card = _card("Target creature you control gains hexproof until end of turn.")
        assert "interaction" in card_roles(card)

    def test_a_creature_that_merely_has_hexproof_does_not(self):
        # Otherwise the interaction count fills up with ordinary creatures.
        card = _card("Hexproof, trample", "Creature — Beast")
        assert "interaction" not in card_roles(card)

    def test_a_sacrifice_outlet_interacts(self):
        card = _card("Sacrifice a creature: Draw a card.", "Enchantment")
        assert "interaction" in card_roles(card)

    def test_a_sacrifice_that_pays_for_a_mana_ability_is_not_interaction(self):
        # Ashnod's Altar: the sacrifice is a mana ability's cost, not a real
        # sacrifice outlet.
        card = _card("Sacrifice a creature: Add {C}{C}.", "Artifact")
        roles = card_roles(card)
        assert "ramp" in roles
        assert "interaction" not in roles


class TestMultipleRoles:
    def test_a_card_can_hold_several_roles(self):
        # Mystic Confluence: draw and bounce on the same card.
        card = _card(
            "Choose three. Draw a card. Return target creature to its owner's "
            "hand. Target creature gets -2/-2 until end of turn."
        )
        roles = card_roles(card)
        assert {"draw", "targeted_removal"} <= roles


class TestRoleCounts:
    def test_counts_are_weighted_by_quantity(self):
        deck = [_item(_card("Draw a card."), quantity=4)]
        assert role_counts(deck)["draw"] == 4

    def test_every_role_is_present_even_at_zero(self):
        from mtg_deck_analyzer.domain.constants import ROLE_ORDER

        assert set(role_counts([])) == set(ROLE_ORDER)


class TestInteractionCount:
    def test_a_card_interacting_two_ways_is_counted_once(self):
        card = _card("Destroy target creature. Destroy all artifacts.", "Sorcery")
        assert {"targeted_removal", "board_wipe"} <= card_roles(card)
        assert interaction_count([_item(card)]) == 1


class TestBaselineReport:
    def _deck(self, ramp=0, draw=0, removal=0, lands=0):
        deck = []
        if ramp:
            deck.append(_item(_card("{T}: Add {C}.", "Artifact"), ramp))
        if draw:
            deck.append(_item(_card("Draw a card."), draw))
        if removal:
            deck.append(_item(_card("Destroy target creature."), removal))
        if lands:
            deck.append(_item(_card("{T}: Add {G}.", "Basic Land — Forest"), lands))
        return deck

    def test_a_deck_inside_the_baseline_has_no_delta(self):
        report = {e["key"]: e for e in baseline_report(self._deck(ramp=10))}
        assert report["ramp"]["count"] == 10
        assert report["ramp"]["delta"] == 0

    def test_too_little_ramp_reports_a_negative_delta(self):
        report = {e["key"]: e for e in baseline_report(self._deck(ramp=6))}
        assert report["ramp"]["delta"] == -4

    def test_too_much_draw_reports_a_positive_delta(self):
        report = {e["key"]: e for e in baseline_report(self._deck(draw=20))}
        assert report["draw"]["delta"] == 8

    def test_lands_are_counted_from_the_type_line(self):
        report = {e["key"]: e for e in baseline_report(self._deck(lands=37))}
        assert report["lands"]["count"] == 37
        assert report["lands"]["delta"] == 0

    def test_the_report_follows_the_configured_order(self):
        from mtg_deck_analyzer.domain.constants import BASELINE_ORDER

        assert [e["key"] for e in baseline_report([])] == BASELINE_ORDER

    def test_interaction_total_is_distinct_from_the_narrow_interaction_role(self):
        # Targeted removal counts toward the broad baseline figure but not
        # the narrow "interaction" role (counterspells/protection/sac
        # outlets) — the two must not share a key and silently collide.
        deck = self._deck(removal=6)
        report = {e["key"]: e for e in baseline_report(deck)}
        assert report["interaction_total"]["count"] == 6
        assert role_counts(deck)["interaction"] == 0
