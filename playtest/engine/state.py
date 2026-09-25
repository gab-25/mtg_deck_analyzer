"""The state of a game in progress."""

from dataclasses import dataclass, field

from .cards import CardInstance, Kind


@dataclass(frozen=True)
class GameRules:
    """The per-format parameters of a game."""

    starting_life: int
    # Combat damage from one commander that eliminates a player (None: untracked).
    commander_damage_limit: int | None
    opening_hand: int = 7
    lands_per_turn: int = 1
    # Each previous cast from the command zone adds this much to the commander's cost.
    commander_tax: int = 2


@dataclass
class PlayerState:
    seat: int
    deck_name: str
    life: int
    library: list[CardInstance] = field(default_factory=list)
    hand: list[CardInstance] = field(default_factory=list)
    battlefield: list[CardInstance] = field(default_factory=list)
    graveyard: list[CardInstance] = field(default_factory=list)
    command: list[CardInstance] = field(default_factory=list)
    commander_casts: int = 0
    lands_played: int = 0
    # Combat damage taken from each opposing commander, by the attacker's seat.
    commander_damage: dict[int, int] = field(default_factory=dict)
    eliminated_round: int | None = None

    @property
    def alive(self) -> bool:
        return self.eliminated_round is None

    def untapped_lands(self) -> list[CardInstance]:
        return [c for c in self.battlefield if c.kind == Kind.LAND and not c.tapped]

    def available_mana(self) -> int:
        # Colors are ignored: every land taps for one generic mana.
        return len(self.untapped_lands())

    def attackers(self) -> list[CardInstance]:
        return [
            c
            for c in self.battlefield
            if c.kind == Kind.CREATURE and not c.tapped and not c.summoning_sick
        ]


@dataclass
class GameState:
    rules: GameRules
    players: list[PlayerState]
    # A round is one turn for every player still in the game.
    round: int = 0
    # The overall turn count, across players.
    turn: int = 0
    active_seat: int = 0
    phase: str = "setup"

    def player(self, seat: int) -> PlayerState:
        return self.players[seat]

    def alive_players(self) -> list[PlayerState]:
        return [p for p in self.players if p.alive]

    def opponents(self, seat: int) -> list[PlayerState]:
        return [p for p in self.players if p.alive and p.seat != seat]
