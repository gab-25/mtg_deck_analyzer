"""An agent that picks uniformly at random: the baseline, and the fallback."""

import random

from ..engine.actions import Action
from .base import Decision


class RandomAgent:
    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)

    def choose(self, view: dict, options: list[Action]) -> Decision:
        return Decision(self.rng.choice(options))
