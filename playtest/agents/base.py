"""The interface between the engine and whoever plays a seat."""

from dataclasses import dataclass
from typing import Protocol

from ..engine.actions import Action


@dataclass(frozen=True)
class Decision:
    action: Action
    # Why the agent chose it, in its own words (empty for agents that don't say).
    reasoning: str = ""
    # Set when the agent could not decide on its own and a fallback chose instead.
    fallback_reason: str = ""


class Agent(Protocol):
    def choose(self, view: dict, options: list[Action]) -> Decision:
        """Picks one of ``options`` given what the seat can see (``view``)."""
        ...
