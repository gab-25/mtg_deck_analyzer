"""The choices an agent is offered, and how they are listed."""

from dataclasses import dataclass, field

from .cards import Kind
from .state import GameState


class Phase:
    MAIN = "main"
    COMBAT = "combat"


class ActionKind:
    PLAY_LAND = "play_land"
    CAST_SPELL = "cast_spell"
    CAST_COMMANDER = "cast_commander"
    ATTACK = "attack"
    # Ends the current phase: leaves the main phase, or skips the attack.
    PASS = "pass"


@dataclass(frozen=True)
class Action:
    kind: str
    card_uid: int | None = None
    target_seat: int | None = None
    # Human-readable description, for agents and the match log.
    label: str = field(default="", compare=False)

    def to_dict(self) -> dict:
        data = {"kind": self.kind, "label": self.label}
        if self.card_uid is not None:
            data["card_id"] = self.card_uid
        if self.target_seat is not None:
            data["target_seat"] = self.target_seat
        return data


def commander_cost(state: GameState, seat: int) -> int | None:
    """What casting ``seat``'s commander costs now, or None if it isn't in the command zone."""
    player = state.player(seat)
    if not player.command:
        return None
    return player.command[0].mana_value + state.rules.commander_tax * player.commander_casts


def legal_actions(state: GameState, seat: int, phase: str) -> list[Action]:
    """Every action ``seat`` may take in ``phase``; passing is always last."""
    player = state.player(seat)
    actions = []

    if phase == Phase.MAIN:
        mana = player.available_mana()
        if player.lands_played < state.rules.lands_per_turn:
            actions += [
                Action(ActionKind.PLAY_LAND, card.uid, label=f"Play land {card.name}")
                for card in player.hand
                if card.kind == Kind.LAND
            ]
        actions += [
            Action(
                ActionKind.CAST_SPELL,
                card.uid,
                label=f"Cast {card.name} (mana value {card.mana_value})",
            )
            for card in player.hand
            if card.kind != Kind.LAND and card.mana_value <= mana
        ]
        cost = commander_cost(state, seat)
        if cost is not None and cost <= mana:
            commander = player.command[0]
            actions.append(
                Action(
                    ActionKind.CAST_COMMANDER,
                    commander.uid,
                    label=f"Cast your commander {commander.name} from the command zone (cost {cost})",
                )
            )
        actions.append(Action(ActionKind.PASS, label="End your main phase"))

    elif phase == Phase.COMBAT:
        attackers = player.attackers()
        if attackers:
            power = sum(c.power for c in attackers)
            actions += [
                Action(
                    ActionKind.ATTACK,
                    target_seat=opponent.seat,
                    label=(
                        f"Attack {opponent.deck_name} (seat {opponent.seat + 1}, "
                        f"{opponent.life} life) with {len(attackers)} creature(s), "
                        f"{power} total power"
                    ),
                )
                for opponent in state.opponents(seat)
            ]
        actions.append(Action(ActionKind.PASS, label="Do not attack"))

    return actions
