"""The rules the engine enforces — and, by omission, the ones it does not.

Supported:

* Opening hand of seven, no mulligans. The commander starts in the command zone.
* Untap, draw (the first player of a two-player game skips the first draw),
  one land per turn, then an attack.
* Every land taps for one generic mana; colors are ignored.
* A spell can be cast when untapped lands cover its mana value. Creatures and
  other permanents enter the battlefield, instants and sorceries go to the
  graveyard with no effect.
* The commander is cast from the command zone for its mana value plus the
  commander tax.
* Attacking sends every creature that can attack at one opponent. There are no
  blockers: each attacker deals damage equal to its power.
* A player is eliminated at 0 life, at the format's commander-damage limit, or
  when drawing from an empty library.

Not supported (yet): the stack and priority, instants at instant speed,
blocking, abilities and card effects, colored mana, mulligans.
"""

from .actions import Action, ActionKind
from .cards import Kind
from .events import Event, EventKind
from .state import GameState, PlayerState


class IllegalAction(Exception):
    """An agent tried something the rules do not allow."""


def _take(zone: list, uid: int):
    for idx, card in enumerate(zone):
        if card.uid == uid:
            return zone.pop(idx)
    raise IllegalAction(f"No card with id {uid} in that zone.")


def _pay(player: PlayerState, amount: int) -> None:
    lands = player.untapped_lands()
    if amount > len(lands):
        raise IllegalAction(f"Cannot pay {amount} mana with {len(lands)} untapped lands.")
    for land in lands[:amount]:
        land.tapped = True


def _enter_battlefield(player: PlayerState, card) -> None:
    card.tapped = False
    card.summoning_sick = card.kind == Kind.CREATURE
    player.battlefield.append(card)


def begin_turn(state: GameState, seat: int) -> None:
    """The untap step: permanents untap and creatures lose summoning sickness."""
    player = state.player(seat)
    for card in player.battlefield:
        card.tapped = False
        card.summoning_sick = False
    player.lands_played = 0


def draw(state: GameState, seat: int) -> list[Event]:
    """``seat`` draws a card; drawing from an empty library eliminates them."""
    player = state.player(seat)
    if not player.library:
        return eliminate(state, seat, "tried to draw from an empty library")
    card = player.library.pop(0)
    player.hand.append(card)
    return [Event(EventKind.DRAW, seat, f"{player.deck_name} draws a card.")]


def eliminate(state: GameState, seat: int, reason: str) -> list[Event]:
    player = state.player(seat)
    if not player.alive:
        return []
    player.eliminated_round = state.round
    return [
        Event(
            EventKind.ELIMINATED,
            seat,
            f"{player.deck_name} is eliminated: {reason}.",
            {"reason": reason},
        )
    ]


def apply(state: GameState, seat: int, action: Action) -> list[Event]:
    """Carries out ``action`` for ``seat`` and returns what happened."""
    player = state.player(seat)

    if action.kind == ActionKind.PASS:
        return []

    if action.kind == ActionKind.PLAY_LAND:
        if player.lands_played >= state.rules.lands_per_turn:
            raise IllegalAction("No land drops left this turn.")
        card = _take(player.hand, action.card_uid)
        if card.kind != Kind.LAND:
            player.hand.append(card)
            raise IllegalAction(f"{card.name} is not a land.")
        player.lands_played += 1
        _enter_battlefield(player, card)
        return [
            Event(EventKind.PLAY_LAND, seat, f"{player.deck_name} plays {card.name}.", {"card": card.name})
        ]

    if action.kind == ActionKind.CAST_SPELL:
        card = next((c for c in player.hand if c.uid == action.card_uid), None)
        if card is None or card.kind == Kind.LAND:
            raise IllegalAction("That card cannot be cast.")
        _pay(player, card.mana_value)
        _take(player.hand, card.uid)
        return [_resolve(player, card, seat)]

    if action.kind == ActionKind.CAST_COMMANDER:
        if not player.command:
            raise IllegalAction("The commander is not in the command zone.")
        cost = player.command[0].mana_value + state.rules.commander_tax * player.commander_casts
        _pay(player, cost)
        card = player.command.pop(0)
        player.commander_casts += 1
        event = _resolve(player, card, seat)
        event.payload["cost"] = cost
        return [event]

    if action.kind == ActionKind.ATTACK:
        return _attack(state, seat, action.target_seat)

    raise IllegalAction(f"Unknown action {action.kind!r}.")


def _resolve(player: PlayerState, card, seat: int) -> Event:
    if card.kind == Kind.SPELL:
        player.graveyard.append(card)
    else:
        _enter_battlefield(player, card)
    return Event(
        EventKind.CAST,
        seat,
        f"{player.deck_name} casts {card.name}.",
        {"card": card.name, "mana_value": card.mana_value, "commander": card.is_commander},
    )


def _attack(state: GameState, seat: int, target_seat: int) -> list[Event]:
    player = state.player(seat)
    target = state.player(target_seat)
    if target_seat == seat or not target.alive:
        raise IllegalAction("That player cannot be attacked.")
    attackers = player.attackers()
    if not attackers:
        raise IllegalAction("No creature can attack.")

    total = sum(c.power for c in attackers)
    events = [
        Event(
            EventKind.ATTACK,
            seat,
            f"{player.deck_name} attacks {target.deck_name} with "
            + ", ".join(c.name for c in attackers)
            + ".",
            {"target_seat": target_seat, "attackers": [c.name for c in attackers]},
        )
    ]
    for card in attackers:
        card.tapped = True
        if card.is_commander:
            target.commander_damage[seat] = target.commander_damage.get(seat, 0) + card.power

    target.life -= total
    events.append(
        Event(
            EventKind.DAMAGE,
            target_seat,
            f"{target.deck_name} takes {total} damage ({target.life} life left).",
            {"amount": total, "life": target.life, "source_seat": seat},
        )
    )

    limit = state.rules.commander_damage_limit
    if target.life <= 0:
        events += eliminate(state, target_seat, "life total reached 0")
    elif limit is not None and target.commander_damage.get(seat, 0) >= limit:
        events += eliminate(state, target_seat, f"{limit} commander damage from {player.deck_name}")
    return events
