"""Hypergeometric probabilities for drawing out of a Magic library.

Pure math, no Magic concepts and nothing beyond :mod:`math`: the library is an
urn, a draw step is a sample without replacement. This is what the
opening-hand and land-drop odds in the statistics panel are built on, and it
lives on its own because none of it is specific to Magic.
"""

from math import comb


def exactly(population: int, successes: int, draws: int, k: int) -> float:
    """Probability of drawing exactly ``k`` of the ``successes`` in ``draws`` cards.

    Out-of-range arguments are answered rather than rejected: drawing more
    cards than the population holds draws the whole population, and asking for
    more successes than can possibly turn up is simply impossible (0.0).
    """
    if population <= 0 or draws <= 0:
        return 1.0 if k == 0 else 0.0

    draws = min(draws, population)
    successes = max(0, min(successes, population))

    # More copies than exist, more than are drawn, or so many drawn that there
    # are not enough non-copies left to fill the hand.
    if k < 0 or k > successes or k > draws or draws - k > population - successes:
        return 0.0

    return (
        comb(successes, k)
        * comb(population - successes, draws - k)
        / comb(population, draws)
    )


def at_least(population: int, successes: int, draws: int, k: int) -> float:
    """Probability of drawing ``k`` or more of the ``successes`` in ``draws`` cards."""
    if k <= 0:
        return 1.0
    draws = min(draws, population) if population > 0 else draws
    successes = max(0, min(successes, population)) if population > 0 else successes
    return sum(
        exactly(population, successes, draws, i)
        for i in range(k, min(successes, draws) + 1)
    )
