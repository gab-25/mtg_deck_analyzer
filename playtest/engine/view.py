"""What one seat is allowed to know about the game."""

from .actions import commander_cost
from .state import GameState


def _cards(zone) -> list:
    return [card.to_dict() for card in zone]


def player_view(state: GameState, seat: int) -> dict:
    """The game from ``seat``'s side of the table, as plain JSON-ready data.

    Hidden information stays hidden: opponents' hands and every library are
    shown as counts only.
    """
    me = state.player(seat)
    return {
        "round": state.round,
        "phase": state.phase,
        "you": {
            "seat": seat,
            "deck": me.deck_name,
            "life": me.life,
            "hand": _cards(me.hand),
            "battlefield": _cards(me.battlefield),
            "command_zone": _cards(me.command),
            "commander_cost": commander_cost(state, seat),
            "graveyard": [c.name for c in me.graveyard],
            "library_count": len(me.library),
            "lands_played_this_turn": me.lands_played,
            "untapped_lands": me.available_mana(),
        },
        "opponents": [
            {
                "seat": p.seat,
                "deck": p.deck_name,
                "life": p.life,
                "hand_count": len(p.hand),
                "library_count": len(p.library),
                "battlefield": _cards(p.battlefield),
                "command_zone": _cards(p.command),
                "commander_damage_taken_from_you": p.commander_damage.get(seat, 0),
            }
            for p in state.opponents(seat)
        ],
    }
