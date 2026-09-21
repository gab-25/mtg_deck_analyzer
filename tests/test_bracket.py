"""Tests for the Commander Bracket estimate (no network, no Django)."""

from mtg_deck_analyzer.domain.bracket import estimate_bracket


def _card(name, *, game_changer=None, rules_text=""):
    """A processed card, shaped the way ``process_cached_card`` returns one.

    ``game_changer=None`` omits the key entirely, which is how a cache entry
    written before Scryfall exposed the flag comes back. It also models a
    card stored in ``Deck.cards`` before this feature existed — the shape the
    data migration and the PDF recompute read — rather than the output of a
    fresh ``process_cached_card``, which always carries the key (possibly as
    ``None``).
    """
    data = {
        "name": name,
        "type_line": "Enchantment",
        "cmc": 3.0,
        "faces": [{"name": name, "mana_cost": "{2}{U}",
                   "type_line": "Enchantment", "rules_text": rules_text}],
    }
    if game_changer is not None:
        data["game_changer"] = game_changer
    return {"quantity": 1, "is_commander": False, "data": data}


def _deck(*cards):
    return list(cards)


class TestBracketTiers:
    def test_a_deck_with_no_signals_is_core(self):
        verdict = estimate_bracket(_deck(_card("Llanowar Elves", game_changer=False)))
        assert verdict["bracket"] == 2
        assert verdict["label"] == "Core"

    def test_three_game_changers_stay_in_upgraded(self):
        verdict = estimate_bracket(_deck(
            _card("Rhystic Study", game_changer=True),
            _card("Smothering Tithe", game_changer=True),
            _card("Cyclonic Rift", game_changer=True),
        ))
        assert verdict["bracket"] == 3
        assert verdict["label"] == "Upgraded"

    def test_four_game_changers_reach_optimized(self):
        verdict = estimate_bracket(_deck(
            _card("Rhystic Study", game_changer=True),
            _card("Smothering Tithe", game_changer=True),
            _card("Cyclonic Rift", game_changer=True),
            _card("Necropotence", game_changer=True),
        ))
        assert verdict["bracket"] == 4
        assert verdict["label"] == "Optimized"

    def test_one_mass_land_denial_card_reaches_optimized(self):
        verdict = estimate_bracket(_deck(_card("Armageddon", game_changer=False)))
        assert verdict["bracket"] == 4
        assert verdict["signals"]["mass_land_denial"] == ["Armageddon"]

    def test_a_single_extra_turn_card_is_not_chaining(self):
        verdict = estimate_bracket(_deck(
            _card("Time Warp", game_changer=False,
                  rules_text="Take an extra turn after this one."),
        ))
        assert verdict["bracket"] == 2

    def test_two_extra_turn_cards_count_as_chaining(self):
        verdict = estimate_bracket(_deck(
            _card("Time Warp", game_changer=False,
                  rules_text="Take an extra turn after this one."),
            _card("Temporal Manipulation", game_changer=False,
                  rules_text="Take an extra turn after this one."),
        ))
        assert verdict["bracket"] == 4
        assert verdict["signals"]["extra_turns"] == [
            "Temporal Manipulation", "Time Warp",
        ]

    def test_never_estimates_exhibition_or_cedh(self):
        empty = estimate_bracket([])
        assert empty["bracket"] == 2
        crowded = estimate_bracket(_deck(
            *[_card(f"Changer {i}", game_changer=True) for i in range(20)],
            _card("Armageddon", game_changer=False),
        ))
        assert crowded["bracket"] == 4


class TestSignalDetection:
    def test_falls_back_to_the_name_list_when_scryfall_flag_is_missing(self):
        verdict = estimate_bracket(_deck(_card("Rhystic Study")))
        assert verdict["signals"]["game_changers"] == ["Rhystic Study"]
        assert verdict["bracket"] == 3

    def test_matches_a_double_faced_card_by_its_front_face(self):
        verdict = estimate_bracket(_deck(
            _card("Tergrid, God of Fright // Tergrid's Lantern"),
        ))
        assert verdict["signals"]["game_changers"] == [
            "Tergrid, God of Fright // Tergrid's Lantern",
        ]

    def test_reports_the_names_behind_every_signal(self):
        verdict = estimate_bracket(_deck(
            _card("Rhystic Study", game_changer=True),
            _card("Armageddon", game_changer=False),
            _card("Time Warp", game_changer=False,
                  rules_text="Take an extra turn after this one."),
        ))
        assert verdict["signals"] == {
            "game_changers": ["Rhystic Study"],
            "mass_land_denial": ["Armageddon"],
            "extra_turns": ["Time Warp"],
        }

    def test_an_empty_deck_reports_empty_signals(self):
        assert estimate_bracket([])["signals"] == {
            "game_changers": [], "mass_land_denial": [], "extra_turns": [],
        }

    def test_an_explicit_false_from_scryfall_outranks_the_name_list(self):
        verdict = estimate_bracket(_deck(_card("Rhystic Study", game_changer=False)))
        assert verdict["signals"]["game_changers"] == []
        assert verdict["bracket"] == 2

    def test_a_card_that_prevents_extra_turns_is_not_a_signal(self):
        # Stranglehold's prohibition text contains "extra turn" as a
        # substring, but it stops extra turns rather than granting one.
        verdict = estimate_bracket(_deck(
            _card(
                "Stranglehold",
                game_changer=False,
                rules_text=(
                    "If an opponent would begin an extra turn, that player "
                    "skips that turn instead."
                ),
            ),
            _card("Time Warp", game_changer=False,
                  rules_text="Take an extra turn after this one."),
        ))
        assert verdict["bracket"] == 2
        assert verdict["signals"]["extra_turns"] == ["Time Warp"]

    def test_a_card_that_grants_multiple_extra_turns_is_counted(self):
        verdict = estimate_bracket(_deck(
            _card("Two-Turn Sorcery", game_changer=False,
                  rules_text="Take two extra turns after this one."),
        ))
        assert verdict["signals"]["extra_turns"] == ["Two-Turn Sorcery"]


class TestFormatGating:
    """The bracket system is Commander's; Duel Commander has none of its own."""

    def test_a_duel_commander_deck_gets_no_verdict(self):
        assert estimate_bracket(_deck(_card("Rhystic Study", game_changer=True)),
                                fmt="duel") == {}

    def test_commander_is_the_default_format(self):
        deck = _deck(_card("Rhystic Study", game_changer=True))
        assert estimate_bracket(deck) == estimate_bracket(deck, fmt="commander")

    def test_a_commander_deck_still_gets_its_verdict(self):
        verdict = estimate_bracket(_deck(_card("Armageddon", game_changer=False)),
                                   fmt="commander")
        assert verdict["bracket"] == 4
