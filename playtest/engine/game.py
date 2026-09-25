"""The game loop: turns, phases, and asking agents what to do."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

from .actions import Action, ActionKind, Phase, legal_actions
from .cards import CardInstance, DeckSpec, Uids
from .events import Event, EventKind
from .rules import IllegalAction, apply, begin_turn, draw
from .state import GameRules, GameState, PlayerState
from .view import player_view

if TYPE_CHECKING:
    from ..agents.base import Agent


class EndReason:
    LAST_STANDING = "last_standing"
    TURN_LIMIT = "turn_limit"


@dataclass
class RecordedEvent:
    """An :class:`Event` stamped with where it happened in the game."""

    seq: int
    round: int
    turn: int
    event: Event


@dataclass
class SeatResult:
    seat: int
    life: int
    eliminated_round: int | None


@dataclass
class GameResult:
    winner_seat: int | None
    end_reason: str
    rounds: int
    seats: list[SeatResult]
    events: list[RecordedEvent] = field(default_factory=list)


class Game:
    """One game between ``len(decks)`` players, each driven by an agent.

    Deterministic for a given ``seed`` as long as the agents are.
    ``on_event`` is called with every :class:`RecordedEvent` as it happens, so a
    caller can persist or stream the game while it runs.
    """

    def __init__(
        self,
        decks: list[DeckSpec],
        agents: list[Agent],
        rules: GameRules,
        *,
        seed: int,
        max_rounds: int = 20,
        max_decisions_per_turn: int = 30,
        on_event: Callable[[RecordedEvent], None] | None = None,
    ):
        if len(decks) != len(agents):
            raise ValueError("Every deck needs an agent.")
        if len(decks) < 2:
            raise ValueError("A game needs at least two players.")
        self.decks = decks
        self.agents = agents
        self.rules = rules
        self.rng = random.Random(seed)
        self.max_rounds = max_rounds
        self.max_decisions_per_turn = max_decisions_per_turn
        self.on_event = on_event
        self.events: list[RecordedEvent] = []
        self.state = self._setup()

    # -- setup -------------------------------------------------------------

    def _setup(self) -> GameState:
        uids = Uids()
        players = []
        for seat, deck in enumerate(self.decks):
            library = [CardInstance(uids.take(), spec) for spec in deck.library]
            self.rng.shuffle(library)
            commander = CardInstance(uids.take(), deck.commander, is_commander=True)
            player = PlayerState(
                seat=seat,
                deck_name=deck.name,
                life=self.rules.starting_life,
                library=library,
                command=[commander],
            )
            opening = min(self.rules.opening_hand, len(library))
            player.hand = [player.library.pop(0) for _ in range(opening)]
            players.append(player)
        return GameState(rules=self.rules, players=players)

    # -- bookkeeping -------------------------------------------------------

    def _record(self, events: list[Event]) -> None:
        for event in events:
            recorded = RecordedEvent(len(self.events) + 1, self.state.round, self.state.turn, event)
            self.events.append(recorded)
            if self.on_event is not None:
                self.on_event(recorded)

    def _over(self) -> bool:
        return len(self.state.alive_players()) <= 1

    # -- the loop ----------------------------------------------------------

    def run(self) -> GameResult:
        state = self.state
        seats = len(state.players)
        first = self.rng.randrange(seats)
        order = [(first + i) % seats for i in range(seats)]
        self._record(
            [
                Event(
                    EventKind.SETUP,
                    None,
                    f"{seats} players at {self.rules.starting_life} life. "
                    f"{state.player(first).deck_name} goes first.",
                    {
                        "first_seat": first,
                        "decks": [p.deck_name for p in state.players],
                        "starting_life": self.rules.starting_life,
                    },
                )
            ]
        )

        for round_no in range(1, self.max_rounds + 1):
            state.round = round_no
            for seat in order:
                if not state.player(seat).alive:
                    continue
                self._take_turn(seat)
                if self._over():
                    return self._finish(EndReason.LAST_STANDING)

        return self._finish(EndReason.TURN_LIMIT)

    def _take_turn(self, seat: int) -> None:
        state = self.state
        player = state.player(seat)
        state.turn += 1
        state.active_seat = seat
        self._record(
            [Event(EventKind.TURN, seat, f"Round {state.round}: {player.deck_name}'s turn.")]
        )

        begin_turn(state, seat)
        # CR 103.8a: in a two-player game the first player skips their first draw.
        if not (state.turn == 1 and len(state.players) == 2):
            self._record(draw(state, seat))
            if not player.alive:
                return

        decisions = 0
        for phase in (Phase.MAIN, Phase.COMBAT):
            state.phase = phase
            while player.alive and not self._over():
                options = legal_actions(state, seat, phase)
                # Nothing to decide: don't spend an agent call on a forced pass.
                if len(options) == 1 and options[0].kind == ActionKind.PASS:
                    break
                if decisions >= self.max_decisions_per_turn:
                    self._record(
                        [
                            Event(
                                EventKind.DECISION_LIMIT,
                                seat,
                                f"{player.deck_name} hit the limit of "
                                f"{self.max_decisions_per_turn} decisions this turn.",
                            )
                        ]
                    )
                    return
                decisions += 1
                action = self._decide(seat, options)
                if action.kind == ActionKind.PASS:
                    break
                self._record(apply(state, seat, action))
                # One attack per turn: combat ends once it has happened.
                if phase == Phase.COMBAT:
                    break
        state.phase = "end"

    def _decide(self, seat: int, options: list[Action]) -> Action:
        player = self.state.player(seat)
        decision = self.agents[seat].choose(player_view(self.state, seat), options)
        if decision.fallback_reason:
            self._record(
                [
                    Event(
                        EventKind.AGENT_FALLBACK,
                        seat,
                        f"{player.deck_name}'s agent fell back to a random choice: "
                        f"{decision.fallback_reason}",
                    )
                ]
            )
        if decision.action not in options:
            raise IllegalAction(f"Agent chose an action that was not offered: {decision.action}")
        if decision.action.kind == ActionKind.PASS or decision.reasoning:
            # A pass leaves no other trace, so it is logged; so is any stated reason.
            self._record(
                [
                    Event(
                        EventKind.PASS if decision.action.kind == ActionKind.PASS else EventKind.DECISION,
                        seat,
                        f"{player.deck_name} chooses: {decision.action.label}.",
                        {"action": decision.action.to_dict()},
                        reasoning=decision.reasoning,
                    )
                ]
            )
        return decision.action

    def _finish(self, reason: str) -> GameResult:
        state = self.state
        alive = state.alive_players()
        winner = alive[0].seat if reason == EndReason.LAST_STANDING and len(alive) == 1 else None
        if winner is not None:
            text = f"{state.player(winner).deck_name} wins in round {state.round}."
        elif reason == EndReason.TURN_LIMIT:
            text = f"Round limit ({self.max_rounds}) reached: the game is a draw."
        else:
            text = "Nobody is left standing: the game is a draw."
        self._record(
            [Event(EventKind.GAME_OVER, winner, text, {"winner_seat": winner, "reason": reason})]
        )
        return GameResult(
            winner_seat=winner,
            end_reason=reason,
            rounds=state.round,
            seats=[SeatResult(p.seat, p.life, p.eliminated_round) for p in state.players],
            events=self.events,
        )
