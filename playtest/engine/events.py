"""What happens in a game, as the engine reports it."""

from dataclasses import dataclass, field


class EventKind:
    SETUP = "setup"
    TURN = "turn"
    DRAW = "draw"
    PLAY_LAND = "play_land"
    CAST = "cast"
    ATTACK = "attack"
    DAMAGE = "damage"
    ELIMINATED = "eliminated"
    # An agent's choice, logged when it carries a stated reason.
    DECISION = "decision"
    PASS = "pass"
    AGENT_FALLBACK = "agent_fallback"
    DECISION_LIMIT = "decision_limit"
    GAME_OVER = "game_over"


@dataclass
class Event:
    kind: str
    # The seat the event is about, or None for table-wide events.
    seat: int | None
    text: str
    payload: dict = field(default_factory=dict)
    # Why the agent chose this, when the event is the outcome of a decision.
    reasoning: str = ""
