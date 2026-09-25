"""Cards as the engine sees them."""

from dataclasses import dataclass, field


class Kind:
    """What the engine does with a card once it resolves."""

    LAND = "land"
    CREATURE = "creature"
    # Artifacts, enchantments, planeswalkers, battles: they stay on the
    # battlefield but do nothing yet.
    PERMANENT = "permanent"
    # Instants, sorceries: they go to the graveyard without an effect yet.
    SPELL = "spell"


@dataclass(frozen=True)
class CardSpec:
    """The printed facts the engine needs about a card."""

    name: str
    kind: str
    mana_value: int = 0
    power: int = 0
    toughness: int = 0


@dataclass(frozen=True)
class DeckSpec:
    """A deck ready to be played: its commander and the other 99 cards."""

    name: str
    commander: CardSpec
    library: tuple[CardSpec, ...]


@dataclass
class CardInstance:
    """One physical card in a game, with its in-game status."""

    uid: int
    spec: CardSpec
    is_commander: bool = False
    tapped: bool = False
    # A creature that came under its controller's control this turn cannot attack.
    summoning_sick: bool = False

    # Convenience accessors, so rules read ``card.kind`` rather than ``card.spec.kind``.
    @property
    def name(self) -> str:
        return self.spec.name

    @property
    def kind(self) -> str:
        return self.spec.kind

    @property
    def mana_value(self) -> int:
        return self.spec.mana_value

    @property
    def power(self) -> int:
        return self.spec.power

    def to_dict(self) -> dict:
        """What an agent is shown about this card."""
        data = {"id": self.uid, "name": self.name, "kind": self.kind, "mana_value": self.mana_value}
        if self.kind == Kind.CREATURE:
            data["power"] = self.spec.power
            data["toughness"] = self.spec.toughness
        if self.tapped:
            data["tapped"] = True
        if self.summoning_sick:
            data["summoning_sick"] = True
        if self.is_commander:
            data["commander"] = True
        return data


@dataclass
class Uids:
    """Hands out card ids unique within one game."""

    next_uid: int = field(default=1)

    def take(self) -> int:
        uid = self.next_uid
        self.next_uid += 1
        return uid
