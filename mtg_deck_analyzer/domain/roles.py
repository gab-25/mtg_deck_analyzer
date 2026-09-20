"""What each card is *for*, matched on its rules text.

Deliberately heuristic and deliberately not a model call: the statistics panel
has to be deterministic, instant and storable with the deck. The patterns are
one readable registry, the way :mod:`.constants` holds the Commander rules.

A card can play several roles at once — Mystic Confluence draws and bounces —
so the counts overlap on purpose.
"""

import re

from .cards import classify_card, rules_text
from .constants import (
    BASELINE_LABELS,
    BASELINE_ORDER,
    EDH_BASELINE,
    ROLE_ORDER,
)

# Basic land type names, so a fetchland ("Search your library for a Forest or
# Plains card...") is recognized as a land search even though it never says
# the word "land" itself.
_BASIC_LAND_TYPES = ("plains", "island", "swamp", "mountain", "forest")
_LAND_WORDS = ("land",) + _BASIC_LAND_TYPES
_LAND_SEARCH_ALTERNATION = "|".join(_LAND_WORDS)

# Subjects that mean the card is a "punisher" triggered by an *opponent's*
# draw (Underworld Dreams: "whenever an opponent draws a card...") rather than
# a draw the deck benefits from. Matched as fixed-width negative lookbehinds
# right before "draws", so "target player draws"/"each player ... draws" (the
# caster's own symmetric or targeted draw) still matches.
_OPPONENT_DRAW_SUBJECTS = (
    r"(?<!an opponent )",
    r"(?<!each opponent )",
    r"(?<!target opponent )",
    r"(?<!another player )",
    r"(?<!than you )",
)
_NOT_OPPONENT_DRAW = "".join(_OPPONENT_DRAW_SUBJECTS)

# One readable registry: role -> the rules-text patterns that give it away.
# Loose by design (they read printed text, not the rules engine), with three
# exceptions: the protection patterns match only what a card *grants*, never a
# creature that simply has hexproof, or the interaction count would fill up
# with ordinary creatures; the draw pattern matches both "draw" (imperative,
# "Draw a card") and third-person "draws" ("Target player draws two cards"),
# since a symmetric wheel or a targeted draw spell is still the deck's own
# draw — but excludes "draws" whose subject is an opponent (see
# _OPPONENT_DRAW_SUBJECTS above), so a punisher payoff like Underworld Dreams
# is never mistaken for a draw source; and the sacrifice pattern excludes a
# sacrifice that pays for a mana ability, which is ramp, not interaction.
ROLE_PATTERNS: dict[str, tuple[str, ...]] = {
    "ramp": (
        r"\badd \{",
        r"\badd (one|two|three|x) mana\b",
        rf"search your library for .{{0,60}}?(?:{_LAND_SEARCH_ALTERNATION})",
        r"put .{0,60}?land card.{0,40}?onto the battlefield",
        r"\bplay an additional land\b",
    ),
    "draw": (
        rf"\b{_NOT_OPPONENT_DRAW}draws? "
        r"(a|one|two|three|four|five|six|seven|x|that many|\d+) cards?\b",
        rf"\b{_NOT_OPPONENT_DRAW}draws? cards equal to\b",
        r"\binvestigate\b",
    ),
    "targeted_removal": (
        r"\b(destroy|exile) target\b",
        r"\bdeals? [\dx]+ damage to (any )?target\b",
        r"\btarget creature gets [-−]\d",
        r"\bfights? target\b",
        r"return target .{0,40}?to (its|their) owner'?s hand",
    ),
    "board_wipe": (
        r"\b(destroy|exile) all\b",
        r"\ball creatures get [-−]\d",
        r"\beach (player|opponent) sacrifices\b",
        r"\bdeals? [\dx]+ damage to each creature\b",
    ),
    "tutor": (r"search your library for",),
    "interaction": (
        r"\bcounter target\b",
        r"\bcounter it unless\b",
        r"\b(gain|gains|have|has) (hexproof|indestructible|shroud|protection from)\b",
        r"\bsacrifice (a|another) (creature|permanent|artifact|enchantment)\b(?!\s*:\s*add\b)",
        r"\bphases? out\b",
    ),
}

_COMPILED = {
    role: tuple(re.compile(pattern) for pattern in patterns)
    for role, patterns in ROLE_PATTERNS.items()
}

# What a "search your library for ..." is looking for, so a land search files as
# ramp and everything else as a tutor.
_SEARCH_RE = re.compile(r"search your library for(.{0,60})", re.S)

# Roles that all count as "interaction" against the deckbuilding baseline.
_INTERACTION_ROLES = frozenset({"targeted_removal", "board_wipe", "interaction"})


def _searches_for_a_spell(text: str) -> bool:
    """Whether any library search looks for something other than a land."""
    return any(
        not any(word in tail for word in _LAND_WORDS)
        for tail in _SEARCH_RE.findall(text)
    )


def card_roles(card_data: dict) -> set:
    """The roles a card plays, possibly several, possibly none."""
    text = rules_text(card_data)
    roles = {
        role
        for role, patterns in _COMPILED.items()
        if any(pattern.search(text) for pattern in patterns)
    }

    # A land is the mana, not what accelerates it; it stays eligible for every
    # other role, so a Field of Ruin still files as removal.
    if classify_card(card_data) == "Land":
        roles.discard("ramp")

    # Fetching a land is ramp, not a tutor.
    if "tutor" in roles and not _searches_for_a_spell(text):
        roles.discard("tutor")

    return roles


def role_counts(processed_cards: list) -> dict:
    """Cards per role, weighted by quantity. Roles overlap, so these do too."""
    counts = {role: 0 for role in ROLE_ORDER}
    for item in processed_cards:
        for role in card_roles(item["data"]):
            counts[role] += item["quantity"]
    return counts


def interaction_count(processed_cards: list) -> int:
    """Cards that interact at all, each counted once however many ways it does."""
    return sum(
        item["quantity"]
        for item in processed_cards
        if card_roles(item["data"]) & _INTERACTION_ROLES
    )


def _land_count(processed_cards: list) -> int:
    return sum(
        item["quantity"]
        for item in processed_cards
        if classify_card(item["data"]) == "Land"
    )


def _delta(count: int, low: int, high: int) -> int:
    """How far outside the baseline range a count sits; 0 when inside it."""
    if count < low:
        return count - low
    if count > high:
        return count - high
    return 0


def baseline_report(processed_cards: list) -> list:
    """The deck against the common EDH baseline, one entry per tracked role."""
    counts = role_counts(processed_cards)
    tallies = {
        **counts,
        "interaction_total": interaction_count(processed_cards),
        "lands": _land_count(processed_cards),
    }

    report = []
    for key in BASELINE_ORDER:
        low, high = EDH_BASELINE[key]
        count = tallies[key]
        report.append(
            {
                "key": key,
                "label": BASELINE_LABELS[key],
                "count": count,
                "low": low,
                "high": high,
                "delta": _delta(count, low, high),
            }
        )
    return report
