"""Tests for the simplified game engine."""

import pytest

from playtest.agents.base import Decision
from playtest.agents.random_agent import RandomAgent
from playtest.engine.actions import Action, ActionKind, Phase, commander_cost, legal_actions
from playtest.engine.cards import CardInstance, CardSpec, Kind
from playtest.engine.events import EventKind
from playtest.engine.game import EndReason, Game
from playtest.engine.rules import IllegalAction, apply, draw
from playtest.engine.state import GameRules
from playtest.engine.view import player_view

from .factories import FOREST, bear, engine_deck

COMMANDER = GameRules(starting_life=40, commander_damage_limit=21)
DUEL = GameRules(starting_life=20, commander_damage_limit=None)


class Scripted:
    """Picks the first offered action of each kind in ``preference``, else passes."""

    def __init__(self, *preference):
        self.preference = preference

    def choose(self, view, options):
        for kind in self.preference:
            for action in options:
                if action.kind == kind:
                    return Decision(action)
        return Decision(options[-1])


class Passive:
    def choose(self, view, options):
        return Decision(options[-1])


def _game(decks=None, agents=None, rules=DUEL, **kwargs):
    decks = decks or [engine_deck("A"), engine_deck("B")]
    agents = agents or [RandomAgent(i) for i in range(len(decks))]
    return Game(decks, agents, rules, seed=kwargs.pop("seed", 1), **kwargs)


def _kinds(game):
    return [e.event.kind for e in game.events]


def _kinds_of(result):
    return [e.event.kind for e in result.events]


def test_setup_deals_seven_and_puts_the_commander_in_the_command_zone():
    game = _game()
    for player in game.state.players:
        assert len(player.hand) == 7
        assert len(player.library) == 92
        assert [c.name for c in player.command] == [f"{player.deck_name} Commander"]
        assert player.life == 20


def test_the_same_seed_replays_the_same_game():
    first = _game(seed=42).run()
    second = _game(seed=42).run()
    assert [e.event.text for e in first.events] == [e.event.text for e in second.events]


def test_different_seeds_shuffle_differently():
    a = _game(seed=1).state.players[0].hand
    b = _game(seed=2).state.players[0].hand
    assert [c.uid for c in a] != [c.uid for c in b]


def test_only_one_land_per_turn():
    game = _game()
    state = game.state
    player = state.player(0)
    player.hand = [CardInstance(1000, FOREST), CardInstance(1001, FOREST)]
    apply(state, 0, legal_actions(state, 0, Phase.MAIN)[0])
    assert not [a for a in legal_actions(state, 0, Phase.MAIN) if a.kind == ActionKind.PLAY_LAND]
    with pytest.raises(IllegalAction):
        apply(state, 0, Action(ActionKind.PLAY_LAND, 1001))


def test_spells_need_enough_untapped_lands():
    game = _game()
    state = game.state
    player = state.player(0)
    player.hand = [CardInstance(1000, bear(mana_value=2))]
    player.battlefield = [CardInstance(1001, FOREST)]
    assert [a.kind for a in legal_actions(state, 0, Phase.MAIN)] == [ActionKind.PASS]
    player.battlefield.append(CardInstance(1002, FOREST))
    cast = legal_actions(state, 0, Phase.MAIN)[0]
    assert cast.kind == ActionKind.CAST_SPELL
    apply(state, 0, cast)
    creature = next(c for c in player.battlefield if c.kind == Kind.CREATURE)
    assert creature.summoning_sick
    assert player.available_mana() == 0


def test_instants_and_sorceries_go_to_the_graveyard():
    game = _game()
    state = game.state
    player = state.player(0)
    player.hand = [CardInstance(1000, CardSpec("Bolt", Kind.SPELL, 1))]
    player.battlefield = [CardInstance(1001, FOREST)]
    apply(state, 0, Action(ActionKind.CAST_SPELL, 1000))
    assert [c.name for c in player.graveyard] == ["Bolt"]


def test_commander_tax_grows_with_each_cast():
    game = _game()
    state = game.state
    player = state.player(0)
    assert commander_cost(state, 0) == 4
    player.battlefield = [CardInstance(1000 + i, FOREST) for i in range(4)]
    apply(state, 0, Action(ActionKind.CAST_COMMANDER, player.command[0].uid))
    assert commander_cost(state, 0) is None
    # Back to the command zone: it now costs 2 more.
    commander = next(c for c in player.battlefield if c.is_commander)
    player.battlefield.remove(commander)
    player.command.append(commander)
    assert commander_cost(state, 0) == 6


def test_attack_deals_unblocked_damage_and_taps_the_attackers():
    game = _game()
    state = game.state
    attacker = CardInstance(1000, bear(power=3))
    state.player(0).battlefield = [attacker]
    [attack, _pass] = legal_actions(state, 0, Phase.COMBAT)
    assert attack.target_seat == 1
    apply(state, 0, attack)
    assert state.player(1).life == 17
    assert attacker.tapped


def test_summoning_sick_creatures_cannot_attack():
    game = _game()
    state = game.state
    state.player(0).battlefield = [CardInstance(1000, bear(), summoning_sick=True)]
    assert [a.kind for a in legal_actions(state, 0, Phase.COMBAT)] == [ActionKind.PASS]


def test_commander_damage_eliminates_at_the_limit():
    game = _game(
        decks=[engine_deck("A"), engine_deck("B"), engine_deck("C")],
        rules=COMMANDER,
    )
    state = game.state
    commander = CardInstance(1000, CardSpec("Big", Kind.CREATURE, 4, 11, 11), is_commander=True)
    state.player(0).battlefield = [commander]
    apply(state, 0, Action(ActionKind.ATTACK, target_seat=1))
    assert state.player(1).alive
    commander.tapped = False
    events = apply(state, 0, Action(ActionKind.ATTACK, target_seat=1))
    assert state.player(1).life == 18  # 40 - 22: alive on life, out on commander damage.
    assert not state.player(1).alive
    assert events[-1].kind == EventKind.ELIMINATED


def test_drawing_from_an_empty_library_eliminates():
    game = _game()
    state = game.state
    state.player(0).library = []
    events = draw(state, 0)
    assert not state.player(0).alive
    assert events[0].kind == EventKind.ELIMINATED


def test_the_first_player_of_a_duel_skips_the_first_draw():
    game = _game(agents=[Passive(), Passive()], max_rounds=1)
    game.run()
    kinds = _kinds(game)
    first_turn = kinds[kinds.index(EventKind.TURN) + 1 : kinds.index(EventKind.TURN, 2)]
    assert EventKind.DRAW not in first_turn


def test_passive_players_draw_at_the_round_limit():
    result = _game(agents=[Passive(), Passive()], max_rounds=3).run()
    assert result.end_reason == EndReason.TURN_LIMIT
    assert result.winner_seat is None
    assert _kinds_of(result)[-1] == EventKind.GAME_OVER


def test_an_aggressive_player_beats_a_passive_one():
    aggro = Scripted(ActionKind.PLAY_LAND, ActionKind.CAST_COMMANDER, ActionKind.CAST_SPELL, ActionKind.ATTACK)
    result = _game(agents=[aggro, Passive()], max_rounds=30).run()
    assert result.end_reason == EndReason.LAST_STANDING
    assert result.winner_seat == 0
    assert result.seats[1].eliminated_round is not None


def test_four_player_game_runs_to_a_result():
    decks = [engine_deck(name) for name in "ABCD"]
    result = _game(decks=decks, rules=COMMANDER, max_rounds=40).run()
    assert result.end_reason in {EndReason.LAST_STANDING, EndReason.TURN_LIMIT}
    assert len(result.seats) == 4


def test_the_decision_limit_ends_a_turn():
    class Stubborn:
        """Never passes the main phase if anything else is offered: loops forever without a cap."""

        def choose(self, view, options):
            return Decision(options[0])

    library = [CardSpec(f"Free {i}", Kind.PERMANENT, 0) for i in range(99)]
    game = _game(
        decks=[engine_deck("A", library=library), engine_deck("B")],
        agents=[Stubborn(), Passive()],
        max_rounds=1,
        max_decisions_per_turn=3,
    )
    game.run()
    assert EventKind.DECISION_LIMIT in _kinds(game)


def test_an_action_that_was_not_offered_is_rejected():
    class Cheater:
        def choose(self, view, options):
            return Decision(Action(ActionKind.CAST_COMMANDER, 1))

    library = [FOREST] * 99
    game = _game(decks=[engine_deck("A", library=library), engine_deck("B", library=library)], agents=[Cheater(), Cheater()])
    with pytest.raises(IllegalAction):
        game.run()


def test_reasoning_is_recorded_on_the_log():
    class Chatty:
        def choose(self, view, options):
            return Decision(options[-1], reasoning="nothing worth doing")

    game = _game(agents=[Chatty(), Chatty()], max_rounds=1)
    game.run()
    assert any(e.event.reasoning == "nothing worth doing" for e in game.events)


def test_the_view_hides_opponents_hands_and_libraries():
    game = _game()
    view = player_view(game.state, 0)
    assert len(view["you"]["hand"]) == 7
    [opponent] = view["opponents"]
    assert opponent["hand_count"] == 7
    assert "hand" not in opponent
    assert "library" not in opponent and "library" not in view["you"]
